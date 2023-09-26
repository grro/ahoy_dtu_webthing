from threading import Thread
from random import randint
from typing import Set, Optional
import re
import requests
from requests import Session
import logging
from time import sleep
from datetime import datetime


class Inverter:

    @staticmethod
    def connect(base_uri: str, inverter_name: str) -> Optional:
        dtu = Dtu.connect(base_uri, {inverter_name})
        return None if len(dtu.inverters) == 0 else dtu.inverters[0]

    def __init__(self, base_uri: str, id: int, channels: int, name: str, serial: str, interval: int):
        self.is_running = True
        self.uri = base_uri
        self.update_uri = re.sub("^/|/$", "", base_uri) + '/api/ctrl'
        self.live_uri = re.sub("^/|/$", "", base_uri) + '/api/record/live'
        self.index_uri = re.sub("^/|/$", "", base_uri) + '/api/index'
        self.config_uri = re.sub("^/|/$", "", base_uri) + '/api/record/config'
        self.inverter_uri = re.sub("^/|/$", "", base_uri) + '/api/inverter/list'

        self.id = id
        self.channel = channels
        self.name = name
        self.serial = serial
        self.interval = interval
        self.p_dc = 0
        self.p_dc1 = 0
        self.p_dc2 = 0
        self.u_dc1 = 0
        self.u_dc2 = 0
        self.i_dc1 = 0
        self.i_dc2 = 0
        self.p_ac = 0
        self.u_ac = 0
        self.i_ac = 0
        self.temp = 0
        self.frequency = 0
        self.efficiency = 0
        self.power_max = 0
        self.power_limit = 0
        self.timestamp_last_success = datetime.fromtimestamp(0)
        self.is_available = False
        self.is_producing = False
        self.listener = None
        self.session = Session()
        Thread(target=self.__periodic_refresh, daemon=True).start()

    @property
    def spare_power(self) -> int:
        if self.p_ac < (self.power_limit * 0.9):
            return 0
        else:
            return self.power_max - self.power_limit

    def close(self):
        self.is_running = False

    def __renew_session(self):
        try:
            self.session.close()
        except Exception as e:
            logging.warning("error occurred closing session " + str(e))
        self.session = Session()

    def __periodic_refresh(self):
        while self.is_running:
            try:
                sleep(randint(0, self.interval))
                self.refresh()
                sleep(int(self.interval/5))
            except Exception as e:
                logging.warning("error occurred refreshing inverter " + self.name + " " + str(e) + " (max " + str(self.power_max) + " watt)")
                sleep(5)
                try:
                    self.__renew_session()
                except Exception as e:
                    logging.warning("error occurred renewing session " + str(e))

    def refresh(self):
        try:
            # fetch inverter info
            response = self.session.get(self.index_uri, timeout=60)
            response.raise_for_status()
            inverter_state = response.json()['inverter']

            timestamp_last_success = datetime.fromtimestamp(inverter_state[self.id]['ts_last_success'])

            previous_is_available = self.is_available
            self.is_available = inverter_state[self.id]['is_avail']
            if previous_is_available != self.is_available:
                logging.info("inverter " + str(self.name) + " is " + ("" if self.is_available else "not ") + "available")

            previous_is_producing = self.is_producing
            self.is_producing = inverter_state[self.id]['is_producing']
            if previous_is_producing != self.is_producing:
                logging.info("inverter " + str(self.name) + " is " + ("" if self.is_producing else "not ") + "producing")

            if self.is_producing:
                # fetch power limit
                response = self.session.get(self.config_uri, timeout=60)
                response.raise_for_status()

                inverter_configs = response.json()['inverter']

                # fetch inverter info
                response = self.session.get(self.inverter_uri, timeout=60)
                response.raise_for_status()
                inverter_infos = response.json()['inverter']

                # fetch temp, power, etc
                response = self.session.get(self.live_uri, timeout=60)
                response.raise_for_status()
                inverter_measures = response.json()['inverter']

                p_ac = 0
                i_ac = 0
                u_ac  =0
                p_dc = 0
                p_dc1 = None
                p_dc2 = None
                u_dc1 = None
                u_dc2 = None
                i_dc1 = None
                i_dc2 = None
                efficiency = None
                temp = 0
                frequency = 0
                power_limit = 0
                power_max = sum(inverter_infos[self.id]['ch_max_pwr'])

                for config in inverter_configs[self.id]:
                    if config['fld'] == 'active_PowerLimit':
                        power_limit_percent = float(config['val'])
                        power_limit = int(power_max * power_limit_percent / 100)

                for measure in inverter_measures[self.id]:
                    if measure['fld'] == 'P_AC':
                        p_ac = float(measure['val'])
                    elif measure['fld'] == 'I_AC':
                        i_ac = float(measure['val'])
                    elif measure['fld'] == 'U_AC':
                        u_ac = float(measure['val'])
                    elif measure['fld'] == 'U_DC':
                        if u_dc1 is None:
                            u_dc1 = float(measure['val'])
                        else:
                            u_dc2 = float(measure['val'])
                    elif measure['fld'] == 'I_DC':
                        if i_dc1 is None:
                            i_dc1 = float(measure['val'])
                        else:
                            i_dc2 = float(measure['val'])
                    elif measure['fld'] == 'P_DC':
                        if p_dc1 is None:
                            p_dc1 = float(measure['val'])
                        elif p_dc2 is None:
                            p_dc2 = float(measure['val'])
                        else:
                            p_dc = float(measure['val'])
                    elif measure['fld'] == 'Efficiency':
                        efficiency = float(measure['val'])
                    elif measure['fld'] == 'Temp':
                        temp = float(measure['val'])
                    elif measure['fld'] == 'F_AC':
                        frequency = float(measure['val'])

                self.update(timestamp_last_success, power_max, power_limit, p_ac, u_ac, i_ac, p_dc, p_dc1, p_dc2, u_dc1, u_dc2, i_dc1, i_dc2, efficiency, temp, frequency)
            else:
                self.update(timestamp_last_success, self.power_max, self.power_limit, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        except Exception as e:
            logging.warning("error occurred getting " + self.name + " inverter data " + str(e))

    def set_power_limit(self, limit_watt: int):
        logging.info("inverter " + self.name + " setting (non-persistent) absolute power limit to " + str(limit_watt) + " Watt")
        try:
            data = {"id": self.id,
                    "cmd": "limit_nonpersistent_absolute",
                    "val": limit_watt}
            resp = requests.post(self.update_uri, json=data)
            resp.raise_for_status()
        except Exception as e:
            logging.warning("error occurred updating power limit of " + self.name + " inverter with " + str(limit_watt) + " " + str(e))

    def update(self, timestamp_last_success: datetime, power_max: int, power_limit: int, p_ac: float, u_ac: float, i_ac: float, p_dc: float, p_dc1:float, p_dc2: float, u_dc1: float, u_dc2: float, i_dc1: float, i_dc2: float, efficiency: float, temp: float, frequency: float):
        if timestamp_last_success != self.timestamp_last_success:
            self.timestamp_last_success = timestamp_last_success
            self.power_max = power_max
            self.power_limit = power_limit
            if self.p_ac != p_ac:
                self.p_ac = p_ac
                logging.debug("inverter " + self.name + " current power: " + str(self.p_ac) + " Watt " +
                              "(power limit " + str(self.power_limit) + " Watt; spare power " + str(self.spare_power) + " Watt)")
            self.u_ac = u_ac
            self.u_dc1 = u_dc1
            self.u_dc2 = u_dc2
            self.i_dc1 = i_dc1
            self.i_dc2 = i_dc2
            self.i_ac = i_ac
            self.p_dc = p_dc
            self.p_dc1 = p_dc1
            self.p_dc2 = p_dc2
            self.efficiency = efficiency
            self.temp = temp
            self.frequency = frequency
            self.__notify_listener()

    def register_listener(self, listener):
        self.listener = listener

    def __notify_listener(self):
        if self.listener is not None:
            self.listener(self)

    def __str__(self):
        return self.name + " " + self.serial + " (P_AC: " + str(self.p_ac) + ", U_AC: " + str(self.u_ac) + ", I_AC: " + str(self.i_ac) + \
                ", P_DC: " + str(self.p_dc) + ", EFFICIENCY: " + str(self.efficiency) +  ")"

    def __repr__(self):
        return  self.__str__()



class Dtu:

    def __init__(self, base_uri: str, inverter_filter: Set[str]):
        self.base_uri = base_uri
        uri = re.sub("^/|/$", "", self.base_uri) + '/api/inverter/list'
        response = requests.get(uri)
        data = response.json()
        interval = int(data['interval'])
        self.inverters = [Inverter(self.base_uri, entry['id'], entry['channels'], entry['name'], entry['serial'], interval)
                          for entry in data['inverter']
                          if len(inverter_filter) == 0 or entry['name'] in inverter_filter]

    def inverter_by_name(self, name: str) -> Optional[Inverter]:
        for inverter in self.inverters:
            if inverter.name == name:
                return inverter
        return None

    @staticmethod
    def connect(base_uri: str, inverter_filter: Set[str] = None):
        return Dtu(base_uri, set() if inverter_filter is None else inverter_filter)

    def close(self):
        for inverter in self.inverters:
            inverter.close()


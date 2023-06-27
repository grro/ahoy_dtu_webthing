from threading import Thread
import re
import requests
import logging
from time import sleep
from datetime import datetime

class Inverter:

    def __init__(self, base_uri: str, id: int, channels: int, name: str, serial: str, interval: int):
        self.is_running = True
        self.update_uri = re.sub("^/|/$", "", base_uri) + '/api/ctrl'
        self.uri = re.sub("^/|/$", "", base_uri) + '/api/record/live'
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
        self.last_update = datetime.fromtimestamp(0)
        self.is_available = False
        self.is_producing = False
        self.listener = None
        Thread(target=self.__periodic_refresh, daemon=True).start()

    def close(self):
        self.is_running = False

    def __periodic_refresh(self):
        while self.is_running:
            try:
                self.refresh()
            except Exception as e:
                logging.warning("error occurred refreshing inverter " + self.name + " " + str(e) + " (max " + str(self.power_max) + " watt)")
            sleep(int(self.interval/2))

    def refresh(self):
        # fetch inverter info
        response = requests.get(self.index_uri)
        inverter_state = response.json()['inverter']

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
            response = requests.get(self.config_uri)
            inverter_configs = response.json()['inverter']

            # fetch inverter info
            response = requests.get(self.inverter_uri)
            inverter_infos = response.json()['inverter']

            # fetch temp, power, etc
            response = requests.get(self.uri)
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

            self.update(power_max, power_limit, p_ac, u_ac, i_ac, p_dc, p_dc1, p_dc2, u_dc1, u_dc2, i_dc1, i_dc2, efficiency, temp, frequency)

    def set_power_limit(self, limit_watt: int):
        logging.info("inverter " + self.name + " set power limit to " + str(limit_watt) + " watt")
        requests.post(self.update_uri, json={"id": self.id, "cmd": "limit_nonpersistent_absolute", "val": limit_watt})

    def update(self, power_max: int, power_limit: int, p_ac: float, u_ac: float, i_ac: float, p_dc: float, p_dc1:float, p_dc2: float, u_dc1: float, u_dc2: float, i_dc1: float, i_dc2: float, efficiency: float, temp: float, frequency: float):
        self.power_max = power_max
        self.power_limit = power_limit
        self.p_ac = p_ac
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
        self.last_update = datetime.now()
        self.__notify_Listener()

    def register_listener(self, listener):
        self.listener = listener

    def __notify_Listener(self):
        if self.listener is not None:
            self.listener()

    def __str__(self):
        return self.name + " " + self.serial + " (P_AC: " + str(self.p_ac) + ", U_AC: " + str(self.u_ac) + ", I_AC: " + str(self.i_ac) + \
                ", P_DC: " + str(self.p_dc) + ", EFFICIENCY: " + str(self.efficiency) +  ")"

    def __repr__(self):
        return  self.__str__()



class Dtu:

    def __init__(self, base_uri: str):
        self.base_uri = base_uri
        uri = re.sub("^/|/$", "", self.base_uri) + '/api/inverter/list'
        response = requests.get(uri)
        data = response.json()
        interval = int(data['interval'])
        self.inverters = [Inverter(self.base_uri, entry['id'], entry['channels'], entry['name'], entry['serial'], interval) for entry in data['inverter']]

    @staticmethod
    def connect(base_uri: str):
        return Dtu(base_uri)

    def close(self):
        for inverter in self.inverters:
            inverter.close()


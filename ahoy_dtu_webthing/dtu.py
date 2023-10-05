from threading import Thread
from random import randint
from dataclasses import dataclass
from typing import Set, Optional, List, Dict
import re
import itertools
import requests
from requests import Session
import logging
from time import sleep
from datetime import datetime
from redzoo.database.simple import SimpleDB


@dataclass
class InverterState:
    p_ac: float
    power_max: int
    power_limit: int
    p_dc1: int
    u_dc1: float
    i_dc1: float
    p_dc2: int
    u_dc2: float
    i_dc2: float


class ChannelSurplus:

    def __init__(self, name: str, is_channel1: bool):
        self.name = name
        self.is_channel1 = is_channel1
        self.db = SimpleDB("inverter_" + name + "_ch1" if is_channel1 else "_ch2")

    @staticmethod
    def key(p_dc: int, u_dc: float) -> str:
        return str(p_dc) + "_" + str(u_dc)

    def record_measure(self, inverter_state_old: InverterState, inverter_state_new: InverterState):
        if inverter_state_old.power_limit == 600 and inverter_state_new.power_limit < inverter_state_old.power_limit:
            u_dc_limited = round(inverter_state_new.u_dc1 if self.is_channel1 else inverter_state_new.u_dc1)
            u_dc_unlimited = round(inverter_state_old.u_dc1 if self.is_channel1 else inverter_state_old.u_dc2)
            diff_dc = 100-round(u_dc_unlimited*100/u_dc_limited)
            if diff_dc > 5:
                p_dc_limited = round(inverter_state_new.p_dc1 if self.is_channel1 else inverter_state_new.p_dc1)
                p_dc_unlimited = round(inverter_state_old.p_dc1 if self.is_channel1 else inverter_state_old.p_dc1)
                if p_dc_unlimited > 0:
                    diff_p = 100-round(p_dc_limited*100/p_dc_unlimited)
                    if diff_p > 10:
                        key = self.key(p_dc_limited, u_dc_limited)
                        records: List[int] = list(self.db.get(key, []))
                        records.append(p_dc_unlimited)
                        if len(records) > 30:
                            records.pop(0)
                        self.db.put(key, records)
                        logging.info(self.name + "#channel" + ("1" if self.is_channel1 else "2") + "  measure added:  " + str(p_dc_limited) + "W/" + str(u_dc_limited) + "V -> " + str(p_dc_unlimited) + "W")

    def measurements(self) -> List[Dict[str, float]]:
        return list(itertools.chain.from_iterable(self.db.get_values()))

    def spare_power(self, current_inverter_state: InverterState) -> int:
        if current_inverter_state.p_ac < (current_inverter_state.power_limit * 0.7):
            # power limit not reached
            return 0
        else:
            # power limit (almost) reached
            p_limit = round(current_inverter_state.power_max/2)
            p_dc_current = current_inverter_state.p_dc1
            u_dc_current = current_inverter_state.u_dc1
            records = sorted(list(self.db.get(self.key(p_dc_current, u_dc_current), [])))
            if len(records) == 0:
                return p_limit - p_dc_current
            else:
                p_dc_predicted = records[int(len(records)*0.5)]
                return p_dc_predicted - p_dc_current


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
        self.irradiation_1 = 0
        self.irradiation_2 = 0
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
        self.power_max = 600
        self.power_limit = self.power_max
        self.timestamp_last_success = datetime.fromtimestamp(0)
        self.timestamp_limit_updated = datetime.now()
        self.is_available = False
        self.is_producing = False
        self.listener = None
        self.channel1_surplus = ChannelSurplus(self.name, True)
        self.channel2_surplus = ChannelSurplus(self.name, False)
        self.__trace = None
        self.session = Session()
        Thread(target=self.__periodic_refresh, daemon=True).start()

    @property
    def spare_power(self) -> int:
        return self.channel1_surplus.spare_power(self.state()) + self.channel2_surplus.spare_power(self.state())

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
                sleep(int(self.interval / 5))
            except Exception as e:
                logging.warning("error occurred refreshing inverter " + self.name + " " + str(e) + " (max " + str(
                    self.power_max) + " watt)")
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
                logging.info(
                    "inverter " + str(self.name) + " is " + ("" if self.is_available else "not ") + "available")

            previous_is_producing = self.is_producing
            self.is_producing = inverter_state[self.id]['is_producing']
            if previous_is_producing != self.is_producing:
                logging.info(
                    "inverter " + str(self.name) + " is " + ("" if self.is_producing else "not ") + "producing")

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
                u_ac = 0
                p_dc = 0
                irradiation_1 = None
                irradiation_2 = None
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
                    elif measure['fld'] == 'Irradiation':
                        if irradiation_1 is None:
                            irradiation_1 = float(measure['val'])
                        else:
                            irradiation_2 = float(measure['val'])
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

                self.update(timestamp_last_success,
                            power_max,
                            power_limit,
                            irradiation_1,
                            irradiation_2,
                            p_ac,
                            u_ac,
                            i_ac,
                            p_dc,
                            p_dc1,
                            p_dc2,
                            u_dc1,
                            u_dc2,
                            i_dc1,
                            i_dc2,
                            efficiency,
                            temp,
                            frequency)
            else:
                self.update(timestamp_last_success,
                            self.power_max,
                            self.power_limit,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0)
        except Exception as e:
            logging.warning("error occurred getting " + self.name + " inverter data " + str(e))

    def __start_limit_updated_trace(self, new_limit_watt: int):
        if self.power_limit == new_limit_watt:  # no change
            return
        if self.__trace is not None:   # terminate running trace (if exists)
            self.__trace.stop()
            self.__trace = None
        elif self.power_limit == self.power_max:  # new limit is max limit
            self.__trace = LimitUpdatedTrace(self)

    def set_power_limit(self, limit_watt: int):
        logging.info(
            "inverter " + self.name + " setting (non-persistent) absolute power limit to " + str(limit_watt) + " Watt")
        self.timestamp_limit_updated = datetime.now()
        try:
            self.__start_limit_updated_trace(limit_watt)
            data = {"id": self.id,
                    "cmd": "limit_nonpersistent_absolute",
                    "val": limit_watt}
            resp = requests.post(self.update_uri, json=data)
            resp.raise_for_status()
        except Exception as e:
            logging.warning(
                "error occurred updating power limit of " + self.name + " inverter with " + str(limit_watt) + " " + str(
                    e))

    def update(self,
               timestamp_last_success: datetime,
               power_max: int,
               power_limit: int,
               irradiation_1: float,
               irradiation_2: float,
               p_ac: float,
               u_ac: float,
               i_ac: float,
               p_dc: float,
               p_dc1: float,
               p_dc2: float,
               u_dc1: float,
               u_dc2: float,
               i_dc1: float,
               i_dc2: float,
               efficiency: float,
               temp: float,
               frequency: float):
        if timestamp_last_success != self.timestamp_last_success:
            self.timestamp_last_success = timestamp_last_success
            self.power_max = power_max
            self.power_limit = power_limit
            self.irradiation_1 = irradiation_1
            self.irradiation_2 = irradiation_2
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
            self.__notify_listener()

    def state(self) -> InverterState:
        return InverterState(p_ac=self.p_ac,
                             power_max=self.power_max,
                             power_limit=self.power_limit,
                             p_dc1=self.p_dc1,
                             u_dc1=self.u_dc1,
                             i_dc1=self.i_dc1,
                             p_dc2=self.p_dc2,
                             u_dc2=self.u_dc2,
                             i_dc2=self.i_dc2)

    def record_measure(self, inverter_state_old: InverterState, inverter_state_new: InverterState):
        self.channel1_surplus.record_measure(inverter_state_old, inverter_state_new)
        self.channel2_surplus.record_measure(inverter_state_old, inverter_state_new)

    @property
    def measurements(self) -> Dict[str, List[Dict[str, float]]]:
        return {
                "channel1" : self.channel1_surplus.measurements(),
                "channel2" : self.channel2_surplus.measurements()
               }

    def register_listener(self, listener):
        self.listener = listener

    def __notify_listener(self):
        if self.listener is not None:
            self.listener(self)

    def __str__(self):
        return self.name + " " + self.serial + " (P_AC: " + str(self.p_ac) + ", U_AC: " + str(
            self.u_ac) + ", I_AC: " + str(self.i_ac) + \
            ", P_DC: " + str(self.p_dc) + ", EFFICIENCY: " + str(self.efficiency) + ")"

    def __repr__(self):
        return self.__str__()


class Dtu:

    def __init__(self, base_uri: str, inverter_filter: Set[str]):
        self.base_uri = base_uri
        uri = re.sub("^/|/$", "", self.base_uri) + '/api/inverter/list'
        response = requests.get(uri)
        data = response.json()
        interval = int(data['interval'])
        self.inverters = [
            Inverter(self.base_uri, entry['id'], entry['channels'], entry['name'], entry['serial'], interval)
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


class LimitUpdatedTrace:

    def __init__(self, inverter: Inverter):
        self.is_still_running = True
        Thread(target=self.__trace, args=(inverter, inverter.state()), daemon=True).start()

    def __trace(self, inverter: Inverter, inverter_state_old: InverterState):
        sleep(2*60)
        if self.is_still_running:
            inverter.record_measure(inverter_state_old, inverter.state())

    def stop(self):
        self.is_still_running = False

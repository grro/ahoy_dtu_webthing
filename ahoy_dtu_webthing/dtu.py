from threading import Thread
import re
import requests
from time import sleep
from datetime import datetime

class Inverter:

    def __init__(self, base_uri: str, id: int, channels: int, name: str, serial: str):
        self.update_uri = re.sub("^/|/$", "", base_uri) + '/api/ctrl'
        self.uri = re.sub("^/|/$", "", base_uri) + '/api/record/live'
        self.config_uri = re.sub("^/|/$", "", base_uri) + '/api/record/config'
        self.inverter_uri = re.sub("^/|/$", "", base_uri) + '/api/inverter/list'

        self.id = id
        self.channel = channels
        self.name = name
        self.serial = serial
        self.p_dc = 0
        self.p_ac = 0
        self.u_ac = 0
        self.i_ac = 0
        self.temp = 0
        self.efficiency = 0
        self.power_max = 0
        self.power_limit = 0
        self.fetch_date = datetime.now()
        self.listener = None
        self.refresh()
        self.set_power_limit(self.power_max)

    def refresh(self):
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
        efficiency = 0
        temp = 0
        power_limit = 0
        power_max = sum(inverter_infos[self.id]['ch_max_pwr'])

        for config in inverter_configs[self.id]:
            if config['fld'] == 'active_PowerLimit':
                power_limit_percent = float(config['val'])
                power_limit = int(power_max * power_limit_percent / 100)

        for measure in inverter_measures[self.id]:
            if measure['fld'] == 'P_AC':
                p_ac = measure['val']
            elif measure['fld'] == 'I_AC':
                i_ac = measure['val']
            elif measure['fld'] == 'U_AC':
                u_ac = measure['val']
            elif measure['fld'] == 'P_DC':
                p_dc = measure['val']
            elif measure['fld'] == 'Efficiency':
                efficiency = measure['val']
            elif measure['fld'] == 'Temp':
                temp = measure['val']

        self.update(power_max, power_limit, p_ac, u_ac, i_ac, p_dc, efficiency, temp)

    def set_power_limit(self, limit_watt: int):
        response = requests.post(self.update_uri, json={"id": self.id, "cmd": "limit_nonpersistent_absolute", "val": limit_watt})
        response = requests.post(self.update_uri, json={"id": self.id, "cmd": "limit_persistent_absolute", "val": limit_watt})
        if response.status_code == 200 and response.json()['success'] == True:
            self.power_limit = limit_watt

    def update(self, power_max: int, power_limit: int, p_ac: int, u_ac: int, i_ac: int, p_dc: int, efficiency: int, temp: int):
        self.power_max = power_max
        self.power_limit = power_limit
        self.p_ac = p_ac
        self.u_ac = u_ac
        self.i_ac = i_ac
        self.p_dc = p_dc
        self.efficiency = efficiency
        self.temp = temp
        self.fetch_date = datetime.now()
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
        self.is_running = True
        self.base_uri = base_uri
        uri = re.sub("^/|/$", "", self.base_uri) + '/api/inverter/list'
        response = requests.get(uri)
        data = response.json()
        self.interval = int(data['interval'])
        self.inverters = [Inverter(self.base_uri, entry['id'], entry['channels'], entry['name'], entry['serial']) for entry in data['inverter']]
        Thread(target=self.__periodic_refresh, daemon=True)

    def __periodic_refresh(self):
        while self.is_running:
            try:
                for inverter in self.inverters:
                    inverter.refresh()
            except Exception as e:
                print(e)
            sleep(self.interval)

    @staticmethod
    def connect(base_uri: str):
        return Dtu(base_uri)

    def close(self):
        self.is_running = False


from webthing import (MultipleThings, Property, Thing, Value, WebThingServer)
import logging
import tornado.ioloop
from ahoy_dtu_webthing.dtu import Dtu, Inverter



class InverterWebThing(Thing):

    # regarding capabilities refer https://iot.mozilla.org/schemas
    # there is also another schema registry http://iotschema.org/docs/full.html not used by webthing
    def __init__(self, description: str, inverter: Inverter):
        Thing.__init__(
            self,
            'urn:dev:ops:Inverter-1',
            ('Inverter ' + inverter.name).strip(),
            ['MultiLevelSensor'],
            description
        )

        self.inverter = inverter

        self.last_update = Value(inverter.last_update.strftime("%Y-%m-%dT%H:%M:%S"))
        self.add_property(
            Property(self,
                     'last_update',
                     self.last_update,
                     metadata={
                         'title': 'last_update',
                         "type": "string",
                         'description': 'The last update [ISO DateTime]',
                         'readOnly': True,
                     }))

        self.name = Value(inverter.name)
        self.add_property(
            Property(self,
                     'name',
                     self.name,
                     metadata={
                         'title': 'name',
                         "type": "string",
                         'description': 'The inverter name',
                         'readOnly': True,
                     }))

        self.serial = Value(inverter.serial)
        self.add_property(
            Property(self,
                     'serial',
                     self.serial,
                     metadata={
                         'title': 'serial',
                         "type": "string",
                         'description': 'The serial number',
                         'readOnly': True,
                     }))

        self.available = Value(inverter.is_available)
        self.add_property(
            Property(self,
                     'is_available',
                     self.available,
                     metadata={
                         'title': 'available',
                         "type": "boolean",
                         'description': 'True, if is available',
                         'readOnly': True,
                     }))

        self.producing = Value(inverter.is_producing)
        self.add_property(
            Property(self,
                 'is_producing',
                     self.producing,
                     metadata={
                     'title': 'producing',
                     "type": "boolean",
                     'description': 'True, if is producing',
                     'readOnly': True,
                 }))

        self.power_max = Value(inverter.power_max)
        self.add_property(
            Property(self,
                     'power_max',
                     self.power_max,
                     metadata={
                         'title': 'power_max',
                         "type": "integer",
                         'description': 'The max power [W]',
                         'readOnly': True,
                     }))

        self.power_limit = Value(inverter.power_limit, inverter.set_power_limit)
        self.add_property(
            Property(self,
                     'power_limit',
                     self.power_limit,
                     metadata={
                         'title': 'power_limit',
                         "type": "integer",
                         'description': 'The power limit [W]',
                         'readOnly': False,
                     }))

        self.temp = Value(inverter.temp)
        self.add_property(
            Property(self,
                     'temp',
                     self.temp,
                     metadata={
                         'title': 'fetch_date',
                         "type": "string",
                         'description': 'The temperature [C]',
                         'readOnly': True,
                     }))

        self.p_dc = Value(inverter.p_dc)
        self.add_property(
            Property(self,
                     'p_dc',
                     self.p_dc,
                     metadata={
                         'title': 'Power DC',
                         "type": "number",
                         'description': 'The power DC [W]',
                         'readOnly': True,
                     }))

        self.u_dc1 = Value(inverter.u_dc1)
        self.add_property(
            Property(self,
                     'u_dc1',
                     self.u_dc1,
                     metadata={
                         'title': 'Voltage DC - Channel 1',
                         "type": "number",
                         'description': 'The voltage DC channel 1 [V]',
                         'readOnly': True,
                     }))

        self.u_dc2 = Value(inverter.u_dc2)
        self.add_property(
            Property(self,
                     'u_dc2',
                     self.u_dc2,
                     metadata={
                         'title': 'Voltage DC - Channel 2',
                         "type": "number",
                         'description': 'The voltage DC channel 2 [V]',
                         'readOnly': True,
                     }))

        self.i_dc1 = Value(inverter.i_dc1)
        self.add_property(
            Property(self,
                     'i_dc1',
                     self.i_dc1,
                     metadata={
                         'title': 'Current DC - Channel 1',
                         "type": "number",
                         'description': 'The current DC channel 1 [A]',
                         'readOnly': True,
                     }))

        self.i_dc2 = Value(inverter.i_dc2)
        self.add_property(
            Property(self,
                     'i_dc2',
                     self.i_dc2,
                     metadata={
                         'title': 'Current DC - Channel 2',
                         "type": "number",
                         'description': 'The current DC channel 2 [A]',
                         'readOnly': True,
                     }))

        self.p_ac = Value(inverter.p_ac)
        self.add_property(
            Property(self,
                     'p_ac',
                     self.p_ac,
                     metadata={
                         'title': 'Power AC',
                         "type": "number",
                         'description': 'The power AC [W]',
                         'readOnly': True,
                     }))

        self.u_ac = Value(inverter.u_ac)
        self.add_property(
            Property(self,
                     'u_ac',
                     self.u_ac,
                     metadata={
                         'title': 'Voltage AC',
                         "type": "number",
                         'description': 'The voltage AC [V]',
                         'readOnly': True,
                     }))

        self.i_ac = Value(inverter.i_ac)
        self.add_property(
            Property(self,
                     'i_ac',
                     self.i_ac,
                     metadata={
                         'title': 'Current AC',
                         "type": "number",
                         'description': 'The current AC [A]',
                         'readOnly': True,
                     }))

        self.efficiency = Value(inverter.efficiency)
        self.add_property(
            Property(self,
                     'efficiency',
                     self.efficiency,
                     metadata={
                         'title': 'Efficiency',
                         "type": "number",
                         'description': 'The efficiency [%]',
                         'readOnly': True,
                     }))

        self.frequency = Value(inverter.frequency)
        self.add_property(
            Property(self,
                     'frequency',
                     self.frequency,
                     metadata={
                         'title': 'frequency',
                         "type": "number",
                         'description': 'The frequency [Hz]',
                         'readOnly': True,
                     }))


        self.ioloop = tornado.ioloop.IOLoop.current()
        self.inverter.register_listener(self.on_value_changed)

    def on_value_changed(self):
        self.ioloop.add_callback(self.__on_value_changed)

    def __on_value_changed(self):
        self.producing.notify_of_external_update(self.inverter.is_producing)
        self.available.notify_of_external_update(self.inverter.is_available)
        self.p_dc.notify_of_external_update(self.inverter.p_dc)
        self.u_dc1.notify_of_external_update(self.inverter.u_dc1)
        self.u_dc2.notify_of_external_update(self.inverter.u_dc2)
        self.i_dc1.notify_of_external_update(self.inverter.i_dc1)
        self.i_dc2.notify_of_external_update(self.inverter.i_dc2)
        self.p_ac.notify_of_external_update(self.inverter.p_ac)
        self.i_ac.notify_of_external_update(self.inverter.i_ac)
        self.u_ac.notify_of_external_update(self.inverter.u_ac)
        self.frequency.notify_of_external_update(self.inverter.frequency)
        self.efficiency.notify_of_external_update(self.inverter.efficiency)
        self.last_update.notify_of_external_update(self.inverter.last_update.strftime("%Y-%m-%dT%H:%M:%S"))
        self.temp.notify_of_external_update(self.inverter.temp)
        self.power_max.notify_of_external_update(self.inverter.power_max)
        self.power_limit.notify_of_external_update(self.inverter.power_limit)


def run_server(description: str, port: int, base_uri: str):
    awning_webthings = [InverterWebThing(description, inverter) for inverter in  Dtu.connect(base_uri).inverters]
    server = WebThingServer(MultipleThings(awning_webthings, 'Inverters'), port=port, disable_host_validation=True)

    logging.info('running webthing server http://localhost:' + str(port))
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info('stopping webthing server')
        server.stop()
        logging.info('done')


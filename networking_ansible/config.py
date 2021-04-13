# Copyright (c) 2018 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg
from oslo_config import types
from oslo_log import log as logging

from networking_ansible import constants as c
CONF = cfg.CONF
LOG = logging.getLogger(__name__)

anet_opts = [
    cfg.StrOpt('coordination_uri',
               default='etcd://127.0.0.1:2379',
               help="backend to use for tooz coordination")
]

cfg.CONF.register_opts(anet_opts, group='ml2_ansible')


class Config(object):

    def __init__(self):
        """Get inventory list from config files

        builds a Network-Runner inventory object
        port_map dictionary and
        and a mac_map dictionary
        according to ansible inventory file yaml definition
        http://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html
        """
        self.inventory = {}
        self.mac_map = {}
        self.port_mappings = {}

        for conffile in CONF.config_file:
            # parse each config file
            sections = {}
            parser = cfg.ConfigParser(conffile, sections)
            try:
                parser.parse()
            except IOError as e:
                LOG.error(str(e))

            # filter out sections that begin with the driver's tag
            hosts = {k: v for k, v in sections.items()
                     if k.startswith(c.DRIVER_TAG)}

            # remember port mappings and remove from the host list
            # mappings come from conf file in format:
            # {'compute_host_id': ['sw_name::testport,sw_name2::testport2']}
            # the list needs to be removed and a dict needs to be
            # returned with a list of tuples of (connection name, port):
            # {'compute_host_id': [('testhost', 'testport')]}
            if c.PORT_MAPPINGS in hosts:
                mappings = hosts[c.PORT_MAPPINGS]
                del hosts[c.PORT_MAPPINGS]

                def format_and_validate_port_mapping(mapping):
                    host_id = mapping[0]
                    ports_lst = []
                    # ensure the mapping is a valid format
                    # format the mapping to a tuple of (switch_name, port_name)
                    ports_split = mapping[1][0].split(',')
                    for port in ports_split:
                        port_split = mapping[1][0].split('::')
                        if len(port_split) == 2:
                            # switch_name::port_name splits to
                            # ['switch_name', 'port_name']
                            ports_lst.append((port_split[0], port_split[1]))
                        else:
                            LOG.error(
                                '{} is not a valid switch_name::port_name '
                                'formated mapping. It will not be available '
                                'for look up. Double check that it is using a '
                                'double colon :: as '
                                'a separator.'.format(mapping))

                    return (host_id, ports_lst)

                mapped = map(format_and_validate_port_mapping,
                             mappings.items())
                # prune out empty mappings
                self.port_mappings = {k: v for k, v in mapped if v}

            # munge the oslo_config data removing the device tag and
            # turning lists with single item strings into strings
            for host in hosts:
                dev_id = host.partition(c.DRIVER_TAG)[2]
                dev_cfg = {k: v[0] for k, v in hosts[host].items()}
                for b in c.BOOLEANS:
                    if b in dev_cfg:
                        dev_cfg[b] = types.Boolean()(dev_cfg[b])
                self.inventory[dev_id] = dev_cfg
                # If mac is defined add it to the mac_map
                if 'mac' in dev_cfg:
                    self.mac_map[dev_cfg['mac'].upper()] = dev_id

        LOG.info('Ansible Host List: %s', ', '.join(self.inventory))
        LOG.debug('Ansible Port Mappings: %s', self.port_mappings)

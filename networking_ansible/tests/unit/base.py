# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import pbr

from neutron.objects import network
from neutron.objects import ports
from neutron.objects import trunk
from neutron.plugins.ml2 import driver_context
from neutron_lib.api.definitions import portbindings
from neutron_lib.api.definitions import provider_net
from oslo_config import cfg
from oslotest import base
from tooz import coordination
from unittest import mock

from networking_ansible import config
from networking_ansible.ml2 import mech_driver

QUOTA_REGISTRIES = (
    "neutron.quota.resource_registry.unregister_all_resources",
    "neutron.quota.resource_registry.register_resource_by_name",
)

COORDINATION = 'networking_ansible.ml2.mech_driver.coordination'


def patch_neutron_quotas():
    """Patch neutron quotas.

    This is to avoid "No resource found" messages printed to stderr from
    quotas Neutron code.
    """
    for func in QUOTA_REGISTRIES:
        mock.patch(func).start()


class MockConfig(object):
    def __init__(self, host=None, mac=None):
        self.inventory = {host: {'mac': mac}} if host and mac else {}
        self.mac_map = {}

    def add_extra_params(self):
        for i in self.inventory:
            self.inventory[i]['stp_edge'] = True

    def add_custom_params(self):
        for i in self.inventory:
            self.inventory[i]['cp_custom'] = 'param'


class BaseTestCase(base.BaseTestCase):
    test_config_files = []
    parse_config = True

    def setUp(self):
        self.addCleanup(mock.patch.stopall)
        super(BaseTestCase, self).setUp()
        if self.parse_config:
            self.setup_config()

        self.ansconfig = config
        self.testhost = 'testhost'
        # using lowercase to ensure case sensitivity is handled correctly
        # the code applys upper() to everything
        self.testmac = '01:23:45:67:89:ab'
        self.testphysnet = 'physnet'

        self.m_config = MockConfig(self.testhost, self.testmac)

    def setup_config(self):
        """Create the default configurations."""
        version_info = pbr.version.VersionInfo('networking_ansible')
        config_files = []
        for conf in self.test_config_files:
            config_files += ['--config-file', conf]
        cfg.CONF(args=config_files,
                 project='networking_ansible',
                 version='%%(prog)s%s' % version_info.release_string())


class NetworkingAnsibleTestCase(BaseTestCase):
    def setUp(self):
        patch_neutron_quotas()
        super(NetworkingAnsibleTestCase, self).setUp()
        config_module = 'networking_ansible.ml2.mech_driver.config.Config'
        with mock.patch(config_module) as m_cfg:
            m_cfg.return_value = self.m_config
            self.mech = mech_driver.AnsibleMechanismDriver()
            with mock.patch(COORDINATION) as m_coord:
                m_coord.get_coordinator = lambda *args: mock.create_autospec(
                    coordination.CoordinationDriver).return_value
                self.mech.initialize()

        self.testsegid = '37'
        self.testsegid2 = '73'
        self.testport = 'switchportid'
        self.testid = 'aaaa-bbbb-cccc'
        self.testid2 = 'cccc-bbbb-aaaa'

        # Define mocked network context
        self.mock_net_context = mock.create_autospec(
            driver_context.NetworkContext).return_value
        self.mock_net_context.current = {
            'id': self.testsegid,
            provider_net.NETWORK_TYPE: 'vlan',
            provider_net.SEGMENTATION_ID: self.testsegid,
            provider_net.PHYSICAL_NETWORK: self.testphysnet,
        }
        self.mock_net_context._plugin_context = 'foo'

        # mocked network orm object
        self.mock_net = mock.create_autospec(
            network.Network).return_value
        self.mock_netseg = mock.Mock(spec=network.NetworkSegment)
        self.mock_netseg.segmentation_id = self.testsegid
        self.mock_netseg.physical_network = self.testphysnet
        self.mock_netseg.network_type = 'vlan'
        self.mock_net.segments = [self.mock_netseg]

        # alternative segment
        self.mock_netseg2 = mock.Mock(spec=network.NetworkSegment)
        self.mock_netseg2.segmentation_id = self.testsegid2
        self.mock_netseg2.physical_network = self.testphysnet
        self.mock_netseg2.network_type = 'vlan'

        # non-physnet segment
        self.mock_netseg3 = mock.Mock(spec=network.NetworkSegment)
        self.mock_netseg3.segmentation_id = self.testsegid2
        self.mock_netseg3.physical_network = 'virtual'
        self.mock_netseg3.network_type = 'vxlan'

        # Local Link Information dicts
        self.lli_no_mac = {
            'local_link_information': [{
                'switch_info': self.testhost,
                'port_id': self.testport,
            }]
        }
        self.lli_no_info = {
            'local_link_information': [{
                'switch_id': self.testmac,
                'port_id': self.testport,
            }]
        }

        # Mocked trunk port objects
        self.mock_port_trunk = mock.Mock(spec=trunk.Trunk)
        self.mock_subport_1 = mock.Mock(spec=trunk.SubPort)
        self.mock_subport_1.segmentation_id = self.testsegid2
        self.mock_port_trunk.sub_ports = [self.mock_subport_1]

        # Mocked port objects
        self.mock_port = mock.create_autospec(
            ports.Port).return_value
        self.mock_port.network_id = self.testid
        self.mock_port.dict = {
            'id': self.testid,
            'mac_address': self.testmac,
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OTHER,
            portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL
        }
        self.mock_port.__getitem__ = mock.Mock(
            side_effect=lambda x: self.mock_port.dict[x])

        self.mock_port2 = mock.create_autospec(
            ports.Port).return_value
        self.mock_port2.network_id = self.testid2
        self.mock_port2.dict = {
            'id': self.testid,
            'mac_address': self.testmac,
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OVS,
            portbindings.VNIC_TYPE: portbindings.VNIC_NORMAL
        }
        self.mock_port2.__getitem__ = mock.Mock(
            side_effect=lambda x: self.mock_port2.dict[x])

        self.mock_ports = [self.mock_port]

        # Mocked port bindings
        self.mock_portbind = mock.Mock(spec=ports.PortBinding)
        self.mock_portbind.profile = self.lli_no_mac
        self.mock_portbind.vnic_type = 'baremetal'
        self.mock_portbind.vif_type = 'other'
        self.mock_port.bindings = [self.mock_portbind]

        # define mocked port context
        self.mock_port_context = mock.create_autospec(
            driver_context.PortContext).return_value
        self.mock_port_context.current = self.mock_port
        self.mock_port_context.original = self.mock_port2
        self.mock_port_context._plugin_context = mock.MagicMock()
        self.mock_port_context.network = mock.Mock()
        self.mock_port_context.network.current = {
            'id': self.testid,
            # TODO(radez) should an int be use here or str ok?
            provider_net.NETWORK_TYPE: 'vlan',
            provider_net.SEGMENTATION_ID: self.testsegid,
            provider_net.PHYSICAL_NETWORK: self.testphysnet
        }
        self.mock_port_context.segments_to_bind = [
            self.mock_port_context.network.current
        ]

# Copyright 2015, Nachi Ueno, NTT I3, Inc.
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
import abc

import netaddr
from oslo_log import log as logging
import oslo_messaging
import six
from neutron_vpnaas.services.vpn.common import constants as vpn_consts

from neutron_vpnaas.services.vpn import service_drivers

LOG = logging.getLogger(__name__)

IPSEC = 'ipsec'
BASE_IPSEC_VERSION = '1.0'


class IPsecVpnDriverCallBack(object):
    """Callback for IPSecVpnDriver rpc."""

    # history
    #   1.0 Initial version

    target = oslo_messaging.Target(version=BASE_IPSEC_VERSION)

    def __init__(self, driver):
        super(IPsecVpnDriverCallBack, self).__init__()
        self.driver = driver

    def get_vpn_services_on_host(self, context, host=None, vpntype=None):
        """Returns the openvpn on the host."""
        plugin = self.driver.service_plugin
        vpnservices = plugin.get_agent_hosting_vpn_services(
            context, host, vpntype)
        return [self.driver.make_vpnservice_dict(context, vpnservice, vpntype)
                for vpnservice in vpnservices]

    def update_status(self, context, status, vpntype=None):
        """Update status of openvpn."""
        plugin = self.driver.service_plugin
        plugin.update_status_by_agent(context, status, vpntype)


class IPsecVpnAgentApi(service_drivers.BaseIPsecVpnAgentApi):
    """Agent RPC API for IPsecVPNAgent."""

    target = oslo_messaging.Target(version=BASE_IPSEC_VERSION)

    def __init__(self, topic, default_version, driver):
        super(IPsecVpnAgentApi, self).__init__(
            topic, default_version, driver)


@six.add_metaclass(abc.ABCMeta)
class BaseIPsecVPNDriver(service_drivers.VpnDriver):
    """Base VPN Service Driver class."""

    def __init__(self, service_plugin, validator=None):
        super(BaseIPsecVPNDriver, self).__init__(service_plugin, validator)
        self.create_rpc_conn()

    @property
    def service_type(self):
        return IPSEC

    @abc.abstractmethod
    def create_rpc_conn(self):
        pass

    def create_ipsec_site_connection(self, context, ipsec_site_connection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, ipsec_site_connection['vpnservice_id'])
        self.agent_rpc.vpnservice_updated(context, vpnservice['router_id'])

    def update_ipsec_site_connection(
            self, context, old_ipsec_site_connection, ipsec_site_connection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, ipsec_site_connection['vpnservice_id'])
        self.agent_rpc.vpnservice_updated(context, vpnservice['router_id'])

    def delete_ipsec_site_connection(self, context, ipsec_site_connection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, ipsec_site_connection['vpnservice_id'])
        self.agent_rpc.vpnservice_updated(context, vpnservice['router_id'])

    def create_ikepolicy(self, context, ikepolicy):
        pass

    def delete_ikepolicy(self, context, ikepolicy):
        pass

    def update_ikepolicy(self, context, old_ikepolicy, ikepolicy):
        pass

    def create_ipsecpolicy(self, context, ipsecpolicy):
        pass

    def delete_ipsecpolicy(self, context, ipsecpolicy):
        pass

    def update_ipsecpolicy(self, context, old_ipsec_policy, ipsecpolicy):
        pass

    def _get_gateway_ips(self, router):
        """Obtain the IPv4 and/or IPv6 GW IP for the router.

        If there are multiples, (arbitrarily) use the first one.
        """
        v4_ip = v6_ip = None
        for fixed_ip in router.gw_port['fixed_ips']:
            addr = fixed_ip['ip_address']
            vers = netaddr.IPAddress(addr).version
            if vers == 4:
                if v4_ip is None:
                    v4_ip = addr
            elif v6_ip is None:
                v6_ip = addr
        return v4_ip, v6_ip

    def create_vpnservice(self, context, vpnservice_dict):
        """Get the gateway IP(s) and save for later use.

        For the reference implementation, this side's tunnel IP (external_ip)
        will be the router's GW IP. IPSec connections will use a GW IP of
        the same version, as is used for the peer, so we will collect the
        first IP for each version (if they exist) and save them.
        """
        vpnservice = self.service_plugin._get_vpnservice(context,
                                                         vpnservice_dict['id'])
        v4_ip, v6_ip = self._get_gateway_ips(vpnservice.router)
        vpnservice_dict['external_v4_ip'] = v4_ip
        vpnservice_dict['external_v6_ip'] = v6_ip
        self.service_plugin.set_external_tunnel_ips(context,
                                                    vpnservice_dict['id'],
                                                    v4_ip=v4_ip, v6_ip=v6_ip)

    def update_vpnservice(self, context, old_vpnservice, vpnservice):
        self.agent_rpc.vpnservice_updated(context, vpnservice['router_id'])

    def delete_vpnservice(self, context, vpnservice):
        self.agent_rpc.vpnservice_updated(context, vpnservice['router_id'])

    def get_external_ip_based_on_peer(self, vpnservice, ipsec_site_con):
        """Use service's external IP, based on peer IP version."""
        vers = netaddr.IPAddress(ipsec_site_con['peer_address']).version
        if vers == 4:
            ip_to_use = vpnservice.external_v4_ip
        else:
            ip_to_use = vpnservice.external_v6_ip
        # TODO(pcm): Add validator to check that connection's peer address has
        # a version that is available in service table, so can fail early and
        # don't need a check here.
        return ip_to_use

    def create_pptpconnection(self, context, pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'])

    def update_pptpconnection(self, context, old_pptpconnection,
                              pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'])

    def delete_pptpconnection(self, context, pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'])

    def create_pptpcredential(
            self, context, pptpcredential, pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'],
                                               credential=pptpcredential)

    def delete_pptpcredential(
            self, context, pptpcredential, pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'],
                                               credential=pptpcredential)

    def update_pptpcredential(
            self, context, pptpcredential, pptpconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, pptpconnection['vpnservice_id'])
        self.pptp_agent_rpc.vpnservice_updated(context,
                                               vpnservice['router_id'],
                                               credential=pptpcredential)

    def create_openvpnconnection(self, context, openvpnconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, openvpnconnection["vpnservice_id"])
        self.openvpn_agent_rpc.vpnservice_updated(context,
                                                  vpnservice["router_id"])

    def update_openvpnconnection(self, context, openvpnconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, openvpnconnection["vpnservice_id"])
        self.openvpn_agent_rpc.vpnservice_updated(context,
                                                  vpnservice["router_id"])

    def delete_openvpnconnection(self, context, openvpnconnection):
        vpnservice = self.service_plugin._get_vpnservice(
            context, openvpnconnection["vpnservice_id"])
        self.openvpn_agent_rpc.vpnservice_updated(context,
                                                  vpnservice["router_id"], openvpnconnection=openvpnconnection)

    def _make_pptp_vpnservice_dict(self, context, vpnservice):
        vpnservice_dict = dict(vpnservice)
        vpnservice_dict['pptpconnections'] = []
        for pptpconnection in vpnservice.pptpconnections:
            pptpconnection_dict = dict(pptpconnection)
            pptpconnection_dict['credentials'] = [dict(cred) for cred in pptpconnection.credentials if
                                                  cred.admin_state_up]
            vpnservice_dict['pptpconnections'].append(pptpconnection_dict)
        return vpnservice_dict

    def _make_openvpn_service_dict(self, context, vpnservice):
        # fengjj:open vpn service here has already adjusted to dict
        return vpnservice

    def make_vpnservice_dict(self, context, vpnservice, vpntype=None):
        if vpntype == vpn_consts.PPTP:
            return self._make_pptp_vpnservice_dict(context, vpnservice)
        elif vpntype == vpn_consts.OPENVPN:
            return self._make_openvpn_service_dict(context, vpnservice)
        else:
            return self._make_ipsec_vpnservice_dict(vpnservice)

    def _make_ipsec_vpnservice_dict(self, vpnservice):
        """Convert vpnservice information for vpn agent.

        also converting parameter name for vpn agent driver
        """
        vpnservice_dict = dict(vpnservice)
        vpnservice_dict['ipsec_site_connections'] = []
        vpnservice_dict['subnet'] = dict(
            vpnservice.subnet)
        # Not removing external_ip from vpnservice_dict, as some providers
        # may be still using it from vpnservice_dict. Will use whichever IP
        # is specified.
        vpnservice_dict['external_ip'] = (
            vpnservice.external_v4_ip or vpnservice.external_v6_ip)
        for ipsec_site_connection in vpnservice.ipsec_site_connections:
            ipsec_site_connection_dict = dict(ipsec_site_connection)
            try:
                netaddr.IPAddress(ipsec_site_connection_dict['peer_id'])
            except netaddr.core.AddrFormatError:
                ipsec_site_connection_dict['peer_id'] = (
                    '@' + ipsec_site_connection_dict['peer_id'])
            ipsec_site_connection_dict['ikepolicy'] = dict(
                ipsec_site_connection.ikepolicy)
            ipsec_site_connection_dict['ipsecpolicy'] = dict(
                ipsec_site_connection.ipsecpolicy)
            vpnservice_dict['ipsec_site_connections'].append(
                ipsec_site_connection_dict)
            peer_cidrs = [
                peer_cidr.cidr
                for peer_cidr in ipsec_site_connection.peer_cidrs]
            ipsec_site_connection_dict['peer_cidrs'] = peer_cidrs
            ipsec_site_connection_dict['external_ip'] = (
                self.get_external_ip_based_on_peer(vpnservice,
                                                   ipsec_site_connection_dict))
        return vpnservice_dict

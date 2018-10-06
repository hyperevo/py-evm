from hvm.chains.base import (
    BaseChain
)

from hp2p.peer import BasePeerPool

from helios.config import ChainConfig
from helios.extensibility import PluginManager
from helios.server import FullServer

from .base import Node


class FullNode(Node):
    _chain: BaseChain = None
    _p2p_server: FullServer = None

    def __init__(self, plugin_manager: PluginManager, chain_config: ChainConfig) -> None:
        super().__init__(plugin_manager, chain_config)
        self._bootstrap_nodes = chain_config.bootstrap_nodes
        self._preferred_nodes = chain_config.preferred_nodes
        self._network_id = chain_config.network_id
        self._node_key = chain_config.nodekey
        self._node_port = chain_config.port
        self._rpc_port = chain_config.rpc_port
        self._max_peers = chain_config.max_peers
        self.notify_resource_available()

    def get_chain(self) -> BaseChain:
        if self._chain is None:
            self._chain = self.chain_class(self.db_manager.get_db())  # type: ignore

        return self._chain

    def get_new_chain(self, chain_address=None):
        if chain_address is None:
            chain_address = self.wallet_address
        return self.chain_class(self.db_manager.get_db(), chain_address)

    # save as [public_key,ip,udp_port,tcp_port]
    def save_node_address_to_local_peer_pool_file(self):
        # path, node_key, ip, udp_port, tcp_port
        path = self.chain_config.local_peer_pool_path
        node_key = self._node_key
        ip = '127.0.0.1'
        udp_port = self._node_port
        tcp_port = self._node_port

        public_key_hex = node_key.public_key.to_hex()

        new_peer = [public_key_hex, ip, udp_port, tcp_port]

        # load existing pool
        try:
            with open(path, 'r') as peer_file:
                existing_peers_raw = peer_file.read()
                existing_peers = json.loads(existing_peers_raw)
            # append the new one
            if not new_peer in existing_peers:
                existing_peers.append(new_peer)

        except FileNotFoundError:
            # No local peers exist yet. lets start a new list.
            existing_peers = []
            existing_peers.append(new_peer)

        # then save
        with open(path, 'w') as peer_file:
            peer_file.write(json.dumps(existing_peers))

    def get_p2p_server(self) -> FullServer:
        if self._p2p_server is None:
            manager = self.db_manager
            self._p2p_server = FullServer(
                self,
                manager.get_chain(),  # type: ignore
                manager.get_chaindb(),  # type: ignore
                manager.get_chain_head_db(),
                manager.get_db(),  # type: ignore
                self._network_id,
                chain_config = self.chain_config,
                max_peers=self._max_peers,
                bootstrap_nodes=self._bootstrap_nodes,
                preferred_nodes=self._preferred_nodes,
                token=self.cancel_token,
                event_bus=self._plugin_manager.event_bus_endpoint
            )
        return self._p2p_server

    def get_peer_pool(self) -> BasePeerPool:
        return self.get_p2p_server().peer_pool

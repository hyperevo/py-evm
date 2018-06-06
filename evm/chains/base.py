from __future__ import absolute_import

from abc import (
    ABCMeta,
    abstractmethod
)
import time
import operator
from typing import (  # noqa: F401
    Any,
    Optional,
    Callable,
    cast,
    Dict,
    Generator,
    Iterator,
    Tuple,
    Type,
    TYPE_CHECKING,
    Union,
)

import logging

from cytoolz import (
    assoc,
    groupby,
)

from eth_typing import (
    Address,
    BlockNumber,
    Hash32,
)

from eth_utils import (
    to_tuple,
    to_set,
)

from evm.db.backends.base import BaseDB
from evm.db.chain import (
    BaseChainDB,
    ChainDB,
)
from evm.constants import (
    BLANK_ROOT_HASH,
)
from evm import constants
from evm.estimators import (
    get_gas_estimator,
)
from evm.exceptions import (
    HeaderNotFound,
    TransactionNotFound,
    ValidationError,
    VMNotFound,
    BlockOnWrongChain,
    CanonicalHeadNotFound,
    NotEnoughTimeBetweenBlocks,
)
from eth_keys.exceptions import (
    BadSignature,
)
from evm.validation import (
    validate_block_number,
    validate_uint256,
    validate_word,
    validate_vm_configuration,
    validate_canonical_address,
    validate_is_queue_block,
)
from evm.rlp.blocks import (
    BaseBlock,
    BaseQueueBlock,
)
from evm.rlp.headers import (
    BlockHeader,
    HeaderParams,
)
from evm.rlp.transactions import (
    BaseTransaction,
    BaseReceiveTransaction
)
from evm.utils.db import (
    apply_state_dict,
)
from evm.utils.datatypes import (
    Configurable,
)
from evm.utils.headers import (
    compute_gas_limit_bounds,
)
from evm.utils.hexadecimal import (
    encode_hex,
)
from evm.utils.rlp import (
    ensure_imported_block_unchanged,
)

from eth_keys import keys
from eth_keys.datatypes import(
        BaseKey,
        PublicKey,
        PrivateKey
)

if TYPE_CHECKING:
    from evm.vm.base import BaseVM  # noqa: F401


# Mapping from address to account state.
# 'balance', 'nonce' -> int
# 'code' -> bytes
# 'storage' -> Dict[int, int]
AccountState = Dict[Address, Dict[str, Union[int, bytes, Dict[int, int]]]]


class BaseChain(Configurable, metaclass=ABCMeta):
    """
    The base class for all Chain objects
    """
    chaindb = None  # type: BaseChainDB
    chaindb_class = None  # type: Type[BaseChainDB]
    vm_configuration = None  # type: Tuple[Tuple[int, Type[BaseVM]], ...]
    
    #
    # Helpers
    #
    @classmethod
    @abstractmethod
    def get_chaindb_class(cls) -> Type[BaseChainDB]:
        raise NotImplementedError("Chain classes must implement this method")

    #
    # Chain API
    #
    @classmethod
    @abstractmethod
    def from_genesis(cls,
                     base_db: BaseDB,
                     genesis_params: Dict[str, HeaderParams],
                     genesis_state: AccountState=None) -> 'BaseChain':
        raise NotImplementedError("Chain classes must implement this method")

    @classmethod
    @abstractmethod
    def from_genesis_header(cls,
                            base_db: BaseDB,
                            genesis_header: BlockHeader) -> 'BaseChain':
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_chain_at_block_parent(self, block: BaseBlock) -> 'BaseChain':
        raise NotImplementedError("Chain classes must implement this method")
    
    #
    # VM API
    #
    @abstractmethod
    def get_vm(self, header: BlockHeader=None) -> 'BaseVM':
        raise NotImplementedError("Chain classes must implement this method")

    @classmethod
    def get_vm_class_for_block_timestamp(cls, timestamp: int = None) -> Type['BaseVM']:
        """
        Returns the VM class for the given block number.
        """
        if timestamp is None:
            timestamp = int(time.time())
        if cls.vm_configuration is None:
            raise AttributeError("Chain classes must define the VMs in vm_configuration")
        validate_uint256(timestamp)
        
        for start_timestamp, vm_class in reversed(cls.vm_configuration):
            if timestamp >= start_timestamp:
                return vm_class
        else:
            raise VMNotFound("No vm available for timestamp #{0}".format(timestamp))

    #
    # Header API
    #
    @abstractmethod
    def create_header_from_parent(self,
                                  parent_header: BlockHeader,
                                  **header_params: HeaderParams) -> BlockHeader:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_block_header_by_hash(self, block_hash: Hash32) -> BlockHeader:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_canonical_head(self):
        raise NotImplementedError("Chain classes must implement this method")

    #
    # Block API
    #
    def get_ancestors(self, limit: int, header: BlockHeader=None) -> Iterator[BaseBlock]:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_block(self) -> BaseBlock:
        raise NotImplementedError("Chain classes must implement this method")

    def get_block_by_hash(self, block_hash: Hash32) -> BaseBlock:
        raise NotImplementedError("Chain classes must implement this method")

    def get_block_by_header(self, block_header: BlockHeader) -> BaseBlock:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_canonical_block_by_number(self, block_number: BlockNumber) -> BaseBlock:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def get_canonical_block_hash(self, block_number):
        raise NotImplementedError("Chain classes must implement this method")

    #
    # Transaction API
    #
    @abstractmethod
    def create_transaction(self, *args: Any, **kwargs: Any) -> BaseTransaction:
        raise NotImplementedError("Chain classes must implement this method")


    @abstractmethod
    def get_canonical_transaction(self, transaction_hash: Hash32) -> BaseTransaction:
        raise NotImplementedError("Chain classes must implement this method")

    #
    # Execution API
    #
#    @abstractmethod
#    def apply_transaction(self, transaction):
#        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def estimate_gas(self, transaction: BaseTransaction, at_header: BlockHeader=None) -> int:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def import_block(self, block: BaseBlock, perform_validation: bool=True) -> BaseBlock:
        raise NotImplementedError("Chain classes must implement this method")

    #
    # Validation API
    #
    @abstractmethod
    def validate_block(self, block: BaseBlock) -> None:
        raise NotImplementedError("Chain classes must implement this method")

    @abstractmethod
    def validate_gaslimit(self, header: BlockHeader) -> None:
        raise NotImplementedError("Chain classes must implement this method")


class Chain(BaseChain):
    """
    A Chain is a combination of one or more VM classes.  Each VM is associated
    with a range of blocks.  The Chain class acts as a wrapper around these other
    VM classes, delegating operations to the appropriate VM depending on the
    current block number.
    """
    logger = logging.getLogger("evm.chain.chain.Chain")
    header = None  # type: BlockHeader
    network_id = None  # type: int
    gas_estimator = None  # type: Callable
    queue_block = None

    chaindb_class = ChainDB  # type: Type[BaseChainDB]

    def __init__(self, base_db: BaseDB, wallet_address: Address, private_key: BaseKey=None) -> None:
        if not self.vm_configuration:
            raise ValueError(
                "The Chain class cannot be instantiated with an empty `vm_configuration`"
            )
        else:
            validate_vm_configuration(self.vm_configuration)
            
        
        validate_canonical_address(wallet_address, "Wallet Address") 
    
        self.private_key = private_key
        self.wallet_address = wallet_address
        self.chaindb = self.get_chaindb_class()(base_db, self.wallet_address)

        try:
            self.header = self.create_header_from_parent(self.get_canonical_head())
        except CanonicalHeadNotFound:
            #this is a new block, lets make a genesis block
            self.logger.debug("Creating new genesis block on chain {}".format(self.wallet_address))
            self.header = self.get_vm_class_for_block_timestamp().create_genesis_block().header
            
        self.queue_block = self.get_block()
        
        if self.gas_estimator is None:
            self.gas_estimator = get_gas_estimator()  # type: ignore
        
    #
    # Helpers
    #
    @classmethod
    def get_chaindb_class(cls) -> Type[BaseChainDB]:
        if cls.chaindb_class is None:
            raise AttributeError("`chaindb_class` not set")
        return cls.chaindb_class
    
        
        
    #
    # Chain API
    #
    @classmethod
    def from_genesis(cls,
                     base_db: BaseDB,
                     wallet_address: Address,
                     private_key: BaseKey,
                     genesis_params: Dict[str, HeaderParams],
                     genesis_state: AccountState=None,
                     ) -> 'BaseChain':
        """
        Initializes the Chain from a genesis state.
        """
        
        genesis_vm_class = cls.get_vm_class_for_block_timestamp()

        account_db = genesis_vm_class.get_state_class().get_account_db_class()(
            base_db,
            BLANK_ROOT_HASH,
        )

        if genesis_state is None:
            genesis_state = {}

        # mutation
        account_db = apply_state_dict(account_db, genesis_state)
        account_db.persist(save_state_root=True)
        

        genesis_header = BlockHeader(**genesis_params)
        return cls.from_genesis_header(base_db, wallet_address = wallet_address, private_key = private_key, genesis_header = genesis_header)

    @classmethod
    def from_genesis_header(cls,
                            base_db: BaseDB,
                            wallet_address: Address,
                            genesis_header: BlockHeader,
                            private_key: BaseKey,
                            ) -> 'BaseChain':
        """
        Initializes the chain from the genesis header.
        """
        signed_genesis_header = genesis_header.get_signed(private_key, cls.network_id)
        chaindb = cls.get_chaindb_class()(base_db, wallet_address = wallet_address)
        chaindb.persist_header(signed_genesis_header)
        return cls(base_db, wallet_address = wallet_address, private_key=private_key)

    def get_chain_at_block_parent(self, block: BaseBlock) -> BaseChain:
        """
        Returns a `Chain` instance with the given block's parent at the chain head.
        """
        try:
            parent_header = self.get_block_header_by_hash(block.header.parent_hash)
        except HeaderNotFound:
            raise ValidationError("Parent ({0}) of block {1} not found".format(
                block.header.parent_hash,
                block.header.hash
            ))

        init_header = self.create_header_from_parent(parent_header)
        return type(self)(self.chaindb.db, self.wallet_address, self.private_key, init_header)
    
    #
    # VM API
    #
    def get_vm(self, header: BlockHeader=None) -> 'BaseVM':
        """
        Returns the VM instance for the given block number.
        """
        if header is None:
            header = self.header
            
        vm_class = self.get_vm_class_for_block_timestamp(header.timestamp)
        
        return vm_class(header=header, chaindb=self.chaindb, private_key=self.private_key, network_id=self.network_id)

    #
    # Header API
    #
    def create_header_from_parent(self, parent_header, **header_params):
        """
        Passthrough helper to the VM class of the block descending from the
        given header.
        """
        return self.get_vm_class_for_block_timestamp().create_header_from_parent(parent_header, **header_params)

    def get_block_header_by_hash(self, block_hash: Hash32) -> BlockHeader:
        """
        Returns the requested block header as specified by block hash.

        Raises BlockNotFound if there's no block header with the given hash in the db.
        """
        validate_word(block_hash, title="Block Hash")
        return self.chaindb.get_block_header_by_hash(block_hash)

    def get_canonical_head(self):
        """
        Returns the block header at the canonical chain head.

        Raises CanonicalHeadNotFound if there's no head defined for the canonical chain.
        """
        return self.chaindb.get_canonical_head()


    #
    # Block API
    #
    @to_tuple
    def get_ancestors(self, limit: int, header: BlockHeader=None) -> Iterator[BaseBlock]:
        """
        Return `limit` number of ancestor blocks from the current canonical head.
        """
        if header is None:
            header = self.header
        lower_limit = max(header.block_number - limit, 0)
        for n in reversed(range(lower_limit, header.block_number)):
            yield self.get_canonical_block_by_number(BlockNumber(n))

    def get_block(self) -> BaseBlock:
        """
        Returns the current TIP block.
        """
        return self.get_vm().block

    def get_block_by_hash(self, block_hash: Hash32) -> BaseBlock:
        """
        Returns the requested block as specified by block hash.
        """
        validate_word(block_hash, title="Block Hash")
        block_header = self.get_block_header_by_hash(block_hash)
        return self.get_block_by_header(block_header)

    def get_block_by_header(self, block_header):
        """
        Returns the requested block as specified by the block header.
        """
        vm = self.get_vm(block_header)
        return vm.block

    def get_canonical_block_by_number(self, block_number: BlockNumber) -> BaseBlock:
        """
        Returns the block with the given number in the canonical chain.

        Raises BlockNotFound if there's no block with the given number in the
        canonical chain.
        """
        validate_uint256(block_number, title="Block Number")
        return self.get_block_by_hash(self.chaindb.get_canonical_block_hash(block_number))

    def get_canonical_block_hash(self, block_number: BlockNumber) -> Hash32:
        """
        Returns the block hash with the given number in the canonical chain.

        Raises BlockNotFound if there's no block with the given number in the
        canonical chain.
        """
        return self.chaindb.get_canonical_block_hash(block_number)
    
    #
    # Queueblock API
    #
    def add_transaction_to_queue_block(self, transaction) -> None:
        if self.queue_block is None:
            self.queue_block = self.get_block()
            
        validate_is_queue_block(self.queue_block, title='self.queue_block')
        
                
        if isinstance(transaction, BaseTransaction):
            if not self.queue_block.contains_transaction(transaction):
                self.queue_block = self.queue_block.add_transaction(transaction)
            else:
                self.logger.debug("found transaction in queueblock already, not adding again")
        else:
            if not self.queue_block.contains_receive_transaction(transaction):
                self.queue_block = self.queue_block.add_receive_transaction(transaction)
            else:
                self.logger.debug("found receive transaction in queueblock already, not adding again")

    def add_transactions_to_queue_block(self, transactions) -> None:
        if not isinstance(transactions, list):
            self.add_transaction_to_queue_block(transactions)
        else:
            for tx in transactions:
                self.add_transaction_to_queue_block(tx)
    
    def sign_queue_block(self, *args: Any, **kwargs: Any) -> BaseQueueBlock:
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().sign_queue_block(*args, **kwargs)
    
    def sign_header(self, *args: Any, **kwargs: Any) -> BlockHeader:
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().sign_header(*args, **kwargs)
    

    #
    # Transaction API
    #
    def get_canonical_transaction(self, transaction_hash: Hash32) -> BaseTransaction:
        """
        Returns the requested transaction as specified by the transaction hash
        from the canonical chain.

        Raises TransactionNotFound if no transaction with the specified hash is
        found in the main chain.
        """
        (block_hash, index, is_receive) = self.chaindb.get_transaction_index(transaction_hash)
        
        block_header = self.get_block_header_by_hash(block_hash)
        
        VM = self.get_vm_class_for_block_timestamp(block_header.timestamp)
        
        if is_receive == False:
            transaction = self.chaindb.get_transaction_by_index_and_block_hash(
                block_hash,
                index,
                VM.get_transaction_class(),
            )
        else:
            transaction = self.chaindb.get_receive_transaction_by_index_and_block_hash(
                block_hash,
                index,
                VM.get_transaction_class(),
            )

        if transaction.hash == transaction_hash:
            return transaction
        else:
            raise TransactionNotFound("Found transaction {} instead of {} in block {} at {}".format(
                encode_hex(transaction.hash),
                encode_hex(transaction_hash),
                block_hash,
                index,
            ))

    def create_transaction(self, *args: Any, **kwargs: Any) -> BaseTransaction:
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().create_transaction(*args, **kwargs)
    
    def create_and_sign_transaction(self, *args: Any, **kwargs: Any) -> BaseTransaction:
        transaction = self.create_transaction(*args, **kwargs)
        signed_transaction = transaction.get_signed(self.private_key, self.network_id)
        return signed_transaction
    
    def create_and_sign_transaction_for_queue_block(self, *args: Any, **kwargs: Any) -> BaseTransaction:
        transaction = self.create_and_sign_transaction(*args, **kwargs)
        self.add_transactions_to_queue_block(transaction)
        return transaction
        
    def create_receive_transaction(self, *args: Any, **kwargs: Any) -> BaseReceiveTransaction:
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().create_receive_transaction(*args, **kwargs)

    def get_receivable_transactions(self, address):
        #from evm.rlp.accounts import TransactionKey
        tx_keys = self.get_vm().state.account_db.get_receivable_transactions(address)
        if len(tx_keys) == 0:
            return False, False
        transactions = []
        for tx_key in tx_keys:
            tx = self.get_canonical_transaction(tx_key.transaction_hash)
            transactions.append(tx)
        return transactions, tx_keys
    
    def create_receivable_signed_transactions(self):
        transactions, tx_keys = self.get_receivable_transactions(self.wallet_address)
        
        if transactions == False:
            return []
        receive_transactions = []
        for i, tx in enumerate(transactions):
            re_tx = self.get_vm().create_receive_transaction(
                    sender_block_hash = tx_keys[i].sender_block_hash, 
                    transaction=tx, 
                    v=0,
                    r=0,
                    s=0,
                    )
            re_tx = re_tx.get_signed(self.private_key, self.network_id)
            receive_transactions.append(re_tx)
        return receive_transactions
    
    def populate_queue_block_with_receive_tx(self):
        receive_tx = self.create_receivable_signed_transactions()
        self.add_transactions_to_queue_block(receive_tx)
        return receive_tx
    #
    # Execution API
    #
#    def apply_transaction(self, transaction):
#        """
#        Applies the transaction to the current tip block.
#
#        WARNING: Receipt and Transaction trie generation is computationally
#        heavy and incurs significant perferomance overhead.
#        """
#        vm = self.get_vm()
#        block = vm.block
#
#        new_header, receipt, computation = vm.apply_transaction(block.header, transaction)
#
#        # since we are building the block locally, we have to persist all the incremental state
#        vm.state.account_db.persist()
#
#        transactions = block.transactions + (transaction, )
#        receipts = block.get_receipts(self.chaindb) + (receipt, )
#
#        new_block = vm.set_block_transactions(block, new_header, transactions, receipts)
#
#        self.header = new_block.header
#
#        return new_block, receipt, computation

    def estimate_gas(self, transaction: BaseTransaction, at_header: BlockHeader=None) -> int:
        """
        Returns an estimation of the amount of gas the given transaction will
        use if executed on top of the block specified by the given header.
        """
        if at_header is None:
            at_header = self.get_canonical_head()
        with self.get_vm(at_header).state_in_temp_block() as state:
            return self.gas_estimator(state, transaction)

    def import_block(self, block: BaseBlock, perform_validation: bool=True) -> BaseBlock:
        """
        Imports a complete block.
        """
        if not block.is_genesis:
            if not self.get_vm().check_time_since_parent_block(block):
                raise NotEnoughTimeBetweenBlocks("not enough time between blocks. We require {} seconds.".format(constants.MIN_TIME_BETWEEN_BLOCKS))
        
        if block.number != self.header.block_number:
            raise ValidationError(
                "Attempt to import block #{0}.  Cannot import block with number "
                "different from the queueblock #{1}.".format(
                    block.number,
                    self.header.block_number,
                )
            )
        

        imported_block = self.get_vm(block.header).import_block(block)
        
        if isinstance(block, self.get_vm().get_queue_block_class()):
            # If it was a queueblock, then the header will have changed after importing
            perform_validation = False
            
        # Validate the imported block.
        if perform_validation:
            ensure_imported_block_unchanged(imported_block, block)
            self.validate_block(imported_block)

        self.chaindb.persist_block(imported_block)
        self.header = self.create_header_from_parent(self.get_canonical_head())
        self.queue_block = None
        self.logger.debug(
            'IMPORTED_BLOCK: number %s | hash %s',
            imported_block.number,
            encode_hex(imported_block.hash),
        )
        return imported_block

    def import_current_queue_block(self):
        
        self.import_block(self.queue_block)
    #
    # Validation API
    #
    def validate_block(self, block: BaseBlock) -> None:
        """
        Performs validation on a block that is either being mined or imported.

        Since block validation (specifically the uncle validation must have
        access to the ancestor blocks, this validation must occur at the Chain
        level.
        """

        self.validate_gaslimit(block.header)

    def validate_gaslimit(self, header: BlockHeader) -> None:
        """
        Validate the gas limit on the given header.
        """
        parent_header = self.get_block_header_by_hash(header.parent_hash)
        low_bound, high_bound = compute_gas_limit_bounds(parent_header)
        if header.gas_limit < low_bound:
            raise ValidationError(
                "The gas limit on block {0} is too low: {1}. It must be at least {2}".format(
                    encode_hex(header.hash), header.gas_limit, low_bound))
        elif header.gas_limit > high_bound:
            raise ValidationError(
                "The gas limit on block {0} is too high: {1}. It must be at most {2}".format(
                    encode_hex(header.hash), header.gas_limit, high_bound))



# This class is a work in progress; its main purpose is to define the API of an asyncio-compatible
# Chain implementation.
class AsyncChain(Chain):

    async def coro_import_block(self,
                                block: BlockHeader,
                                perform_validation: bool=True) -> BaseBlock:
        raise NotImplementedError()

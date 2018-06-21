import time
from abc import (
    ABCMeta,
    abstractmethod
)
from uuid import UUID
import logging
from lru import LRU
from typing import Set, Tuple  # noqa: F401

from eth_typing import Hash32

import rlp

from trie import (
    BinaryTrie,
    HexaryTrie,
)

from eth_hash.auto import keccak
from eth_utils import encode_hex

from trie.constants import (
    BLANK_HASH,
)

from evm.constants import (
    BLANK_ROOT_HASH,
    EMPTY_SHA3,
    SLASH_WALLET_ADDRESS,
    NUMBER_OF_HEAD_HASH_TO_SAVE,
    TIME_BETWEEN_HEAD_HASH_SAVE,
)
from evm.db.batch import (
    BatchDB,
)
from evm.db.cache import (
    CacheDB,
)
from evm.db.journal import (
    JournalDB,
)
from evm.rlp.accounts import (
    Account,
    TransactionKey,
)
from evm.validation import (
    validate_is_bytes,
    validate_uint256,
    validate_canonical_address,
)

from evm.utils.numeric import (
    int_to_big_endian,
)
from evm.utils.padding import (
    pad32,
)

from evm.db.schema import SchemaV1

from .hash_trie import HashTrie

from evm.rlp.sedes import(
    trie_root,
    hash32,
)

from rlp.sedes import (
    big_endian_int,
    CountableList,
    binary,
    List
)
from eth_utils import (
    int_to_big_endian,
    big_endian_to_int,
)
import itertools
import math
from evm.exceptions import (
    InvalidHeadRootTimestamp,        
)

from evm.utils.rlp import make_mutable

from sortedcontainers import SortedList

# Use lru-dict instead of functools.lru_cache because the latter doesn't let us invalidate a single
# entry, so we'd have to invalidate the whole cache in _set_account() and that turns out to be too
# expensive.
account_cache = LRU(2048)


class ConsensusDB():

    logger = logging.getLogger('evm.db.chain_head.ChainHeadDB')

    def __init__(self, db, root_hash=BLANK_HASH):
        """
        Binary trie database for storing the hash of the head block of each wallet address.
        """
        self.db = db
        self._batchdb = BatchDB(db)

 
    #
    # Block hash API
    #
    
  

    #
    # Record and discard API
    #
    def persist(self) -> None:
        self._batchdb.commit(apply_deletes=True)

        
    
    
    
    
    
    
    
    
    
    
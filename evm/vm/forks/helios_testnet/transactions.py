import rlp

from evm.utils.numeric import (
    int_to_big_endian,
)
from evm.utils.transactions import (
    create_transaction_signature,
    extract_chain_id,
    is_eip_155_signed_transaction,
    extract_transaction_sender,
    validate_transaction_signature,
)

from evm.constants import (
    GAS_TX,
    GAS_TXCREATE,
    GAS_TXDATAZERO,
    GAS_TXDATANONZERO,
    CREATE_CONTRACT_ADDRESS,
)


from evm.validation import (
    validate_lt_secpk1n2,
    validate_uint256,
    validate_is_integer,
    validate_is_bytes,
    validate_lt_secpk1n,
    validate_lte,
    validate_gte,
    validate_canonical_address,
)

from evm.rlp.transactions import (
    BaseTransaction,
    BaseReceiveTransaction,
)

from rlp.sedes import (
    big_endian_int,
    binary,
)
from evm.rlp.sedes import (
    address,
    hash32,
)




class HeliosTestnetTransaction(BaseTransaction):

    def check_signature_validity(self):
        validate_transaction_signature(self)

    def get_sender(self):
        return extract_transaction_sender(self)

    def get_intrinsic_gas(self):
        return _get_helios_testnet_intrinsic_gas(self)
    
    
    def validate(self):
        validate_uint256(self.nonce, title="Transaction.nonce")
        validate_uint256(self.gas_price, title="Transaction.gas_price")
        validate_uint256(self.gas, title="Transaction.gas")
        if self.to != CREATE_CONTRACT_ADDRESS:
            validate_canonical_address(self.to, title="Transaction.to")
        validate_uint256(self.value, title="Transaction.value")
        validate_is_bytes(self.data, title="Transaction.data")

        validate_uint256(self.v, title="Transaction.v")
        validate_uint256(self.r, title="Transaction.r")
        validate_uint256(self.s, title="Transaction.s")

        validate_lt_secpk1n(self.r, title="Transaction.r")
        validate_gte(self.r, minimum=1, title="Transaction.r")
        validate_lt_secpk1n(self.s, title="Transaction.s")
        validate_gte(self.s, minimum=1, title="Transaction.s")

        validate_gte(self.v, minimum=self.v_min, title="Transaction.v")
        validate_lte(self.v, maximum=self.v_max, title="Transaction.v")
        
        super(HeliosTestnetTransaction, self).validate()
        validate_lt_secpk1n2(self.s, title="Transaction.s")


    @property
    def chain_id(self):
        if is_eip_155_signed_transaction(self):
            return extract_chain_id(self.v)


    @property
    def v_min(self):
        if is_eip_155_signed_transaction(self):
            return 35 + (2 * self.chain_id)


    @property
    def v_max(self):
        if is_eip_155_signed_transaction(self):
            return 36 + (2 * self.chain_id)

    def get_signed(self, private_key, chain_id):
        v,r,s = create_transaction_signature(self, private_key, chain_id)
        return self.copy(
                v=v,
                r=r,
                s=s,
                )

def _get_helios_testnet_intrinsic_gas(transaction):
    num_zero_bytes = transaction.data.count(b'\x00')
    num_non_zero_bytes = len(transaction.data) - num_zero_bytes
    if transaction.to == CREATE_CONTRACT_ADDRESS:
        create_cost = GAS_TXCREATE
    else:
        create_cost = 0
    return (
        GAS_TX +
        num_zero_bytes * GAS_TXDATAZERO +
        num_non_zero_bytes * GAS_TXDATANONZERO +
        create_cost
    )
    
    
class HeliosTestnetReceiveTransaction(BaseReceiveTransaction):

    fields = [
        ('sender_block_hash', hash32),
        ('transaction', HeliosTestnetTransaction),
        ('v', big_endian_int),
        ('r', big_endian_int),
        ('s', big_endian_int),
    ]
    
    def check_signature_validity(self):
        validate_transaction_signature(self)

    def get_receiver(self):
        return extract_transaction_sender(self)
  
    def validate(self):
 
        validate_uint256(self.v, title="Transaction.v")
        validate_uint256(self.r, title="Transaction.r")
        validate_uint256(self.s, title="Transaction.s")

        validate_lt_secpk1n(self.r, title="Transaction.r")
        validate_gte(self.r, minimum=1, title="Transaction.r")
        validate_lt_secpk1n(self.s, title="Transaction.s")
        validate_gte(self.s, minimum=1, title="Transaction.s")

        validate_gte(self.v, minimum=self.v_min, title="Transaction.v")
        validate_lte(self.v, maximum=self.v_max, title="Transaction.v")
        
        super(HeliosTestnetReceiveTransaction, self).validate()
        validate_lt_secpk1n2(self.s, title="Transaction.s")



    @property
    def chain_id(self):
        if is_eip_155_signed_transaction(self):
            return extract_chain_id(self.v)


    @property
    def v_min(self):
        if is_eip_155_signed_transaction(self):
            return 35 + (2 * self.chain_id)


    @property
    def v_max(self):
        if is_eip_155_signed_transaction(self):
            return 36 + (2 * self.chain_id)
        
    def get_signed(self, private_key, chain_id):
        v,r,s = create_transaction_signature(self, private_key, chain_id)
        return self.copy(
                v=v,
                r=r,
                s=s,
                )

        


from enum import StrEnum


class DealStatus(StrEnum):
    PENDING = 'PENDING'
    ACTIVE = 'ACTIVE'
    DISPUTE = 'DISPUTE'
    DISPUTE_WAITING = 'DISPUTE_WAITING'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'


class WithdrawStatus(StrEnum):
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class DisputeResolution(StrEnum):
    BUYER = 'BUYER'
    SELLER = 'SELLER'
    SPLIT = 'SPLIT'
    RESUME = 'RESUME'

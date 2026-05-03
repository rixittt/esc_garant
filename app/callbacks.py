from aiogram.filters.callback_data import CallbackData


class DealActionCb(CallbackData, prefix='deal'):
    action: str
    deal_id: int


class DealPageCb(CallbackData, prefix='dealspg'):
    page: int


class DealRateCb(CallbackData, prefix='rate'):
    deal_id: int
    stars: int


class AdminWithdrawCb(CallbackData, prefix='wdr'):
    action: str
    withdraw_id: int


class AdminWithdrawPageCb(CallbackData, prefix='wdrpg'):
    page: int


class AdminDisputeCb(CallbackData, prefix='dsp'):
    action: str
    deal_id: int


class AdminSettingCb(CallbackData, prefix='stg'):
    key: str


class CreateDealRoleCb(CallbackData, prefix='cdr'):
    action: str


class WithdrawMethodCb(CallbackData, prefix='wdm'):
    method: str


class DepositCb(CallbackData, prefix='dep'):
    action: str
    deposit_id: int


class AdminTxPageCb(CallbackData, prefix='txpg'):
    page: int


class AdminTxCb(CallbackData, prefix='tx'):
    tx_id: int


class AdminDisputePageCb(CallbackData, prefix='dsppg'):
    page: int


class AdminDisputeTargetCb(CallbackData, prefix='dsptgt'):
    deal_id: int
    target: str


class BroadcastCb(CallbackData, prefix='bc'):
    action: str


class AdminUserCb(CallbackData, prefix='ausr'):
    action: str
    user_id: int


class AdminDealPageCb(CallbackData, prefix='adpg'):
    page: int


class AdminDealCb(CallbackData, prefix='ad'):
    deal_id: int


class AdminManageCb(CallbackData, prefix='amg'):
    action: str
    tg_id: int

from aiogram.fsm.state import State, StatesGroup


class CreateDealSG(StatesGroup):
    seller = State()
    amount = State()
    terms = State()


class OpenDisputeSG(StatesGroup):
    reason = State()


class DealChatSG(StatesGroup):
    message = State()


class WithdrawSG(StatesGroup):
    amount = State()
    method = State()
    requisites = State()


class DepositSG(StatesGroup):
    amount = State()


class BroadcastSG(StatesGroup):
    text = State()
    photo = State()


class AdminWithdrawSG(StatesGroup):
    tx_info = State()


class AdminDisputeMoreInfoSG(StatesGroup):
    target = State()
    text = State()


class AdminSettingSG(StatesGroup):
    key = State()
    value = State()


class AdminUserSearchSG(StatesGroup):
    query = State()


class AdminUserBalanceSG(StatesGroup):
    amount = State()


class AdminManageAdminsSG(StatesGroup):
    command = State()


class AdminBanReasonSG(StatesGroup):
    reason = State()

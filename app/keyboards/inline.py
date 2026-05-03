from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import AdminDealCb, AdminDealPageCb, AdminDisputeCb, AdminDisputePageCb, AdminDisputeTargetCb, AdminManageCb, AdminSettingCb, AdminTxCb, AdminTxPageCb, AdminUserCb, AdminWithdrawCb, AdminWithdrawPageCb, BroadcastCb, CreateDealRoleCb, DealActionCb, DealPageCb, DealRateCb, DepositCb, WithdrawMethodCb


def create_deal_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='⚡ Start', callback_data=CreateDealRoleCb(action='start').pack())],
            [InlineKeyboardButton(text='❌ Hide', callback_data=CreateDealRoleCb(action='hide').pack())],
        ]
    )


def deals_list_kb(deals: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for d in deals:
        rows.append([InlineKeyboardButton(text=f"#{d['public_id']} • {d['status']} • ${d['amount']}", callback_data=DealActionCb(action='open', deal_id=d['id']).pack())])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=DealPageCb(page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=DealPageCb(page=page + 1).pack()))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_sent_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Cancel', callback_data=DealActionCb(action='offer_cancel', deal_id=deal_id).pack())]])


def seller_response_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Accept', callback_data=DealActionCb(action='accept', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='❌ Decline', callback_data=DealActionCb(action='decline', deal_id=deal_id).pack())],
        ]
    )


def active_deal_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🕊 Send message', callback_data=DealActionCb(action='sendmsg', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='✅ Complete', callback_data=DealActionCb(action='complete', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='🔴 Cancel', callback_data=DealActionCb(action='cancel', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='⚖️ Open dispute', callback_data=DealActionCb(action='dispute', deal_id=deal_id).pack())],
        ]
    )


def complete_confirm_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Complete', callback_data=DealActionCb(action='complete_confirm', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='⬅️ Back', callback_data=DealActionCb(action='open', deal_id=deal_id).pack())],
        ]
    )


def cancel_confirm_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='❌ Confirm cancel', callback_data=DealActionCb(action='cancel_confirm', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='⬅️ Back', callback_data=DealActionCb(action='open', deal_id=deal_id).pack())],
        ]
    )


def reply_msg_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📨 Reply', callback_data=DealActionCb(action='sendmsg', deal_id=deal_id).pack())]])


def rating_kb(deal_id: int) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=f'{i}⭐️', callback_data=DealRateCb(deal_id=deal_id, stars=i).pack()) for i in range(1, 6)]
    return InlineKeyboardMarkup(inline_keyboard=[row])








def deposit_invoice_kb(deposit_id: int, pay_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='💳 Pay via CryptoBot', url=pay_url)],
            [InlineKeyboardButton(text='✅ I have paid', callback_data=DepositCb(action='check', deposit_id=deposit_id).pack())],
            [InlineKeyboardButton(text='❌ Cancel', callback_data=DepositCb(action='cancel', deposit_id=deposit_id).pack())],
        ]
    )
def admin_withdraws_list_kb(items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for w in items:
        rows.append([InlineKeyboardButton(text=f"#{w['id']} • ${w['amount']} -> ${w['net_amount']}", callback_data=AdminWithdrawCb(action='open', withdraw_id=w['id']).pack())])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminWithdrawPageCb(page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminWithdrawPageCb(page=page + 1).pack()))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
def withdraw_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='USDT BEP20', callback_data=WithdrawMethodCb(method='BEP20').pack())],
            [InlineKeyboardButton(text='USDT ERC20', callback_data=WithdrawMethodCb(method='ERC20').pack())],
        ]
    )


def withdraw_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Cancel', callback_data='withdraw:cancel')]])


def pending_deal_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Cancel', callback_data=DealActionCb(action='cancel_pending', deal_id=deal_id).pack())]])


def admin_transactions_list_kb(items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for t in items:
        rows.append([InlineKeyboardButton(text=f"Deposit #{t['id']} • @{t['username'] or t['tg_id']} ({t['tg_id']}) • ${t['amount_usd']}", callback_data=AdminTxCb(tx_id=t['id']).pack())])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminTxPageCb(page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminTxPageCb(page=page + 1).pack()))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_deals_list_kb(items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for d in items:
        rows.append([InlineKeyboardButton(text=f"#{d['public_id']} • {d['status']} • ${d['amount']}", callback_data=AdminDealCb(deal_id=d['id']).pack())])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminDealPageCb(page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminDealPageCb(page=page + 1).pack()))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_disputes_list_kb(items: list[dict], page: int, total_pages: int, mode: str = 'active') -> InlineKeyboardMarkup:
    rows = []
    rows.append(
        [
            InlineKeyboardButton(text='🟢 Active' if mode == 'active' else 'Active', callback_data=AdminDisputePageCb(page=1).pack() + ':active'),
            InlineKeyboardButton(text='✅ Resolved' if mode == 'resolved' else 'Resolved', callback_data=AdminDisputePageCb(page=1).pack() + ':resolved'),
        ]
    )
    for d in items:
        rows.append([InlineKeyboardButton(text=f"Deal #{d['public_id']} • {d['status']}", callback_data=AdminDisputeCb(action=f'open_{mode}', deal_id=d['id']).pack())])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminDisputePageCb(page=page - 1).pack() + f':{mode}'))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminDisputePageCb(page=page + 1).pack() + f':{mode}'))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dispute_target_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Buyer', callback_data=AdminDisputeTargetCb(deal_id=deal_id, target='buyer').pack())],
            [InlineKeyboardButton(text='Seller', callback_data=AdminDisputeTargetCb(deal_id=deal_id, target='seller').pack())],
            [InlineKeyboardButton(text='Both', callback_data=AdminDisputeTargetCb(deal_id=deal_id, target='both').pack())],
        ]
    )
def admin_withdraw_kb(withdraw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Approve', callback_data=AdminWithdrawCb(action='approve', withdraw_id=withdraw_id).pack())],
            [InlineKeyboardButton(text='❌ Reject', callback_data=AdminWithdrawCb(action='reject', withdraw_id=withdraw_id).pack())],
        ]
    )


def admin_dispute_kb(deal_id: int, buyer_ref: str, seller_ref: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f'✅ Resolve for {buyer_ref}', callback_data=AdminDisputeCb(action='buyer', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text=f'✅ Resolve for {seller_ref}', callback_data=AdminDisputeCb(action='seller', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='⚖️ A Split 50/50', callback_data=AdminDisputeCb(action='split', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='🕒 Request More Info', callback_data=AdminDisputeCb(action='more', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='❌ Cancel Dispute (Resume Deal)', callback_data=AdminDisputeCb(action='resume', deal_id=deal_id).pack())],
            [InlineKeyboardButton(text='⬅️ Back to Active Disputes', callback_data='admin:disputes:active:1')],
        ]
    )


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Withdraw Fee %', callback_data=AdminSettingCb(key='withdraw_fee_percent').pack())],
            [InlineKeyboardButton(text='Withdraw Fee Fixed $', callback_data=AdminSettingCb(key='withdraw_fee_amount').pack())],
            [InlineKeyboardButton(text='Min Deal Amount', callback_data=AdminSettingCb(key='min_deal_amount').pack())],
            [InlineKeyboardButton(text='Min Withdraw Amount', callback_data=AdminSettingCb(key='min_withdraw_amount').pack())],
            [InlineKeyboardButton(text='Support Username', callback_data=AdminSettingCb(key='support_admin_username').pack())],
            [InlineKeyboardButton(text='Monitor Chat', callback_data=AdminSettingCb(key='monitor_chat').pack())],
            [InlineKeyboardButton(text='Manage Admins', callback_data=AdminSettingCb(key='manage_admins').pack())],
        ]
    )


def broadcast_skip_photo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='➡️ Send without photo', callback_data=BroadcastCb(action='skip_photo').pack())],
        ]
    )


def manage_admins_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='➕ Add admin', callback_data=AdminManageCb(action='add', tg_id=0).pack())],
            [InlineKeyboardButton(text='➖ Remove admin', callback_data=AdminManageCb(action='remove', tg_id=0).pack())],
            [InlineKeyboardButton(text='⬅️ Back', callback_data=AdminManageCb(action='settings', tg_id=0).pack())],
        ]
    )


def manage_admins_remove_list_kb(items: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"@{x['username'] or x['tg_id']} ({x['tg_id']})", callback_data=AdminManageCb(action='confirm_remove', tg_id=x['tg_id']).pack())] for x in items]
    rows.append([InlineKeyboardButton(text='⬅️ Back', callback_data=AdminManageCb(action='menu', tg_id=0).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manage_admin_confirm_kb(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Confirm remove', callback_data=AdminManageCb(action='do_remove', tg_id=tg_id).pack())],
            [InlineKeyboardButton(text='⬅️ Back', callback_data=AdminManageCb(action='remove', tg_id=0).pack())],
        ]
    )


def admin_user_profile_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_btn = InlineKeyboardButton(
        text='✅ Unban' if is_banned else '🚫 Ban',
        callback_data=AdminUserCb(action='unban' if is_banned else 'ban', user_id=user_id).pack(),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='➕ Add balance', callback_data=AdminUserCb(action='add_balance', user_id=user_id).pack()),
                InlineKeyboardButton(text='➖ Subtract balance', callback_data=AdminUserCb(action='sub_balance', user_id=user_id).pack()),
            ],
            [
                InlineKeyboardButton(text='📂 Deals', callback_data=AdminUserCb(action='deals_1', user_id=user_id).pack()),
                InlineKeyboardButton(text='📥 Deposits', callback_data=AdminUserCb(action='deposits_1', user_id=user_id).pack()),
            ],
            [InlineKeyboardButton(text='📤 Withdrawals', callback_data=AdminUserCb(action='withdraws_1', user_id=user_id).pack())],
            [ban_btn],
            [InlineKeyboardButton(text='🔄 Refresh', callback_data=AdminUserCb(action='refresh', user_id=user_id).pack())],
        ]
    )


def admin_user_deals_kb(user_id: int, items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{d['public_id']} • {d['status']} • ${d['amount']}",
                callback_data=AdminUserCb(action=f'deal_open_{d["id"]}', user_id=user_id).pack(),
            )
        ]
        for d in items
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminUserCb(action=f'deals_{page - 1}', user_id=user_id).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminUserCb(action=f'deals_{page + 1}', user_id=user_id).pack()))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_deposits_kb(user_id: int, items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Deposit #{d['id']} • ${d['amount_usd']} • {d['status']}",
                callback_data=AdminUserCb(action=f'deposit_open_{d["id"]}', user_id=user_id).pack(),
            )
        ]
        for d in items
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminUserCb(action=f'deposits_{page - 1}', user_id=user_id).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminUserCb(action=f'deposits_{page + 1}', user_id=user_id).pack()))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_withdraws_kb(user_id: int, items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Withdraw #{w['id']} • ${w['amount']} • {w['status']}",
                callback_data=AdminUserCb(action=f'withdraw_open_{w["id"]}', user_id=user_id).pack(),
            )
        ]
        for w in items
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='⬅️', callback_data=AdminUserCb(action=f'withdraws_{page - 1}', user_id=user_id).pack()))
    nav.append(InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='➡️', callback_data=AdminUserCb(action=f'withdraws_{page + 1}', user_id=user_id).pack()))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)

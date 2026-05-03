def calc_offset(page: int, page_size: int) -> int:
    return max(page - 1, 0) * page_size

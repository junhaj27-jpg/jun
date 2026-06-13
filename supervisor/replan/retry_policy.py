# 최대 재시도 횟수와 재시도 가능 여부 정책을 정의합니다.


def can_replan(current_round: int, max_round: int) -> bool:
    return current_round < max_round

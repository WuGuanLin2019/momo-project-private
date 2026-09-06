def lerp(start:float, end:float, t:float):
    return start + (end - start) * t

def push_to(cur:float, end:float, interval:float):
    if cur < end:
        return min(cur + interval, end)
    if cur > end:
        return max(cur - interval, end)
    return end
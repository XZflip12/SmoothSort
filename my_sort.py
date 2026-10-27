"""Модуль my_sort: плавная сортировка (smoothsort) Дейкстры"""
#pylint: disable=W0123,R0914,C0415,E0401,C0415,C0104,R0915
import argparse
import sys
import random

def _leonardo(n):
    nums = [1, 1]
    while len(nums) < n:
        nums.append(nums[-1] + nums[-2] + 1)
    return nums


LP = _leonardo(60)


def _sift(arr, root, order, less):
    while order > 1:
        r = root - 1
        l = root - 1 - LP[order - 2]
        if less(arr[r], arr[l]):
            child, child_order = l, order - 1
        else:
            child, child_order = r, order - 2
        if not less(arr[root], arr[child]):
            return
        arr[root], arr[child] = arr[child], arr[root]
        root, order = child, child_order


def _trinkle(arr, trees, i, less):
    root, order = trees[i]
    while i > 0:
        prev_root, _ = trees[i - 1]
        if not less(arr[root], arr[prev_root]):
            break
        if order >= 2:
            r = root - 1
            l = root - 1 - LP[order - 2]
            if not less(arr[l], arr[prev_root]) or not less(arr[r], arr[prev_root]):
                break
        arr[prev_root], arr[root] = arr[root], arr[prev_root]
        i -= 1
        root, order = trees[i]
    _sift(arr, root, order, less)


def _build_forest(arr, less):
    forest = []
    for i in range(len(arr)):
        if len(forest) >= 2 and forest[-2][1] == forest[-1][1] + 1:
            forest.pop()
            _, k = forest.pop()
            forest.append((i, k + 1))
        elif forest and forest[-1][1] == 1:
            forest.append((i, 0))
        else:
            forest.append((i, 1))
        _trinkle(arr, forest, len(forest) - 1, less)
    return forest

class _TracedList(list):
    def __init__(self, data, trace):
        super().__init__(data)
        self._trace = trace
        self._writes = 0
        self._trace.append([x[0] for x in self])

    def __setitem__(self, i, value):
        super().__setitem__(i, value)
        self._writes += 1
        if self._writes % 2 == 0:
            self._trace.append([x[0] for x in self])


def _sort(array, reverse, key, cmp, trace):
    if cmp is None:
        def base_less(a, b):
            return a < b
    else:
        def base_less(a, b):
            return bool(cmp(a, b))

    items = [(key(x) if key else x, i, x) for i, x in enumerate(array)]
    if trace is not None:
        items = _TracedList(items, trace)

    def less(a, b):
        ka, kb = a[0], b[0]
        if reverse:
            ka, kb = kb, ka
        if base_less(ka, kb):
            return True
        if base_less(kb, ka):
            return False
        return a[1] < b[1]

    forest = _build_forest(items, less)
    for _ in range(len(items)):
        root, order = forest.pop()
        if order >= 2:
            r = root - 1
            l = root - 1 - LP[order - 2]
            forest.append((l, order - 1))
            _trinkle(items, forest, len(forest) - 1, less)
            forest.append((r, order - 2))
            _trinkle(items, forest, len(forest) - 1, less)

    return [item[2] for item in items]


def my_sort(array, reverse=False, key=None, cmp=None):
    """Возвращает новый отсортированный список."""
    return _sort(array, reverse, key, cmp, None)


# ---------- CLI ----------

_SAFE = {
    "len": len, "abs": abs, "int": int, "float": float, "str": str,
    "min": min, "max": max, "sum": sum, "sorted": sorted,
}
_KEYS = {**_SAFE, "lower": str.lower, "upper": str.upper}


def _parse_key(text):
    if text in _KEYS:
        return _KEYS[text]
    return _parse_lambda(text)


def _parse_lambda(text):
    func = eval(text, {"__builtins__": {}}, dict(_SAFE))
    if not callable(func):
        raise argparse.ArgumentTypeError(f"не функция: {text}")
    return func


def _convert(values, kind, key=None):
    if not values:
        return []
    if kind == "str":
        return list(values)

    casts = [int, float] if kind == "auto" else [{"int": int, "float": float}[kind]]
    for cast in casts:
        try:
            converted = [cast(v) for v in values]
            if key is not None:
                key(converted[0])
            return converted
        except (ValueError, TypeError, AttributeError):
            continue

    if kind == "auto":
        return list(values)
    raise SystemExit(f"тип {kind} несовместим с данными или переданным ключом (-k)")

class _Synth:
    """Неблокирующий синтезатор: тоны смешиваются в callback потока звука."""

    RATE = 44100
    TONE_MS = 40

    def __init__(self, np_module, sd_module, levels_count):
        self._np = np_module
        self._n = levels_count
        self._cache = {}
        self._active = []  # [массив тона, позиция]
        self._stream = sd_module.OutputStream(
            samplerate=self.RATE, channels=1, dtype="float32",
            callback=self._callback)
        self._stream.start()

    def _tone(self, level):
        """Тон для уровня; считается один раз и кэшируется."""
        if level not in self._cache:
            np = self._np
            size = int(self.RATE * self.TONE_MS / 1000)
            t = np.arange(size) / self.RATE
            wave = np.sin(2 * np.pi * (200 + 1000 * level / self._n) * t)
            edge = size // 4
            env = np.ones(size)
            env[:edge] = np.linspace(0, 1, edge)
            env[-edge:] = np.linspace(1, 0, edge)
            self._cache[level] = (0.15 * wave * env).astype(np.float32)
        return self._cache[level]

    def play(self, levels):
        """Добавляет тоны в микс (список append потокобезопасен)."""
        for level in levels[:4]:  # больше 4 голосов сразу не нужно
            if len(self._active) < 16:
                self._active.append([self._tone(level), 0])

    def _callback(self, outdata, frames, _time, _status):
        np = self._np
        outdata.fill(0)
        for voice in self._active[:]:
            tone, pos = voice
            chunk = tone[pos:pos + frames]
            outdata[:len(chunk), 0] += chunk
            voice[1] += frames
            if voice[1] >= len(tone):
                self._active.remove(voice)
        np.clip(outdata, -1, 1, out=outdata)

    def close(self):
        """Останавливает поток звука."""
        self._stream.stop()
        self._stream.close()


def _visualize(trace, final, delay, sound=False):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    import numpy as np
    import sounddevice as sd

    n = len(final)
    synth = None
    if sound:
        synth = _Synth(np, sd, n)

    steps = len(trace)

    try:
        raw_min = min(min(frame) for frame in trace)
        raw_max = max(max(frame) for frame in trace)
    except TypeError:
        raw_min, raw_max = 0, n

    if raw_min >= 0:
        y_lim_bottom = 0
        y_lim_top = raw_max * 1.05 if raw_max > 0 else 1.0
    else:
        span = raw_max - raw_min
        pad = max(span * 0.05, 1)
        y_lim_bottom = raw_min - pad
        y_lim_top = max(0, raw_max) + pad

    val_span = raw_max - raw_min if raw_max != raw_min else 1
    def to_sound_level(val):
        if isinstance(val, (int, float)):
            return int((val - raw_min) / val_span * (n - 1))
        return 0

    interval = max(delay, 25)
    stride = max(1, round(interval / max(delay, 1)))
    shots = list(range(0, steps, stride))
    if shots[-1] != steps - 1:
        shots.append(steps - 1)

    fig, ax = plt.subplots()

    first_frame = trace[0]
    bars = ax.bar(range(n), first_frame, color="steelblue", width=0.8)

    if raw_min < 0:
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.7)

    ax.set_title("Smoothsort")
    ax.set_ylim(y_lim_bottom, y_lim_top)
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_xticks(range(n))
    ax.set_xticklabels([str(x) for x in final] if n <= 30 else [])

    last = [-1]

    def set_bar_value(bar, val):
        if val >= 0:
            bar.set_y(0)
            bar.set_height(val)
        else:
            bar.set_y(val)
            bar.set_height(-val)

    def update(f):
        fresh = f != last[0]
        last[0] = f

        if f < len(shots):
            cur = trace[shots[f]]
            prev = trace[shots[f - 1]] if f else cur
            changed_audio = []

            for pos, (bar, val) in enumerate(zip(bars, cur)):
                set_bar_value(bar, val)
                diff = val != prev[pos]
                bar.set_color("tomato" if diff else "steelblue")
                if diff:
                    changed_audio.append(to_sound_level(val))

            ax.set_xlabel(f"шаг {shots[f] + 1}/{steps}")
            if synth and fresh and changed_audio:
                synth.play(changed_audio)
        else:
            i = f - len(shots)
            for pos, (bar, val) in enumerate(zip(bars, trace[-1])):
                set_bar_value(bar, val)
                bar.set_color("seagreen" if pos <= i else "steelblue")

            ax.set_xlabel("проверка порядка")
            if synth and fresh:
                synth.play([to_sound_level(trace[-1][i])])

        return bars

    _anim = FuncAnimation(fig, update, frames=len(shots) + n,
                          interval=interval, repeat=False)
    plt.show()
    if synth:
        synth.close()

def _read_values(args, parser):
    """Возвращает список строк-элементов из выбранного источника."""
    if args.random is not None:
        if args.random < 1:
            parser.error("--random: размер должен быть не меньше 1")
        rng = random.Random(args.seed)
        return [str(rng.randint(args.min, args.max))
                for _ in range(args.random)]
    if args.input:
        try:
            with open(args.input, encoding="utf-8") as file:
                return file.read().split()
        except OSError as err:
            parser.error(f"не удалось прочитать {args.input}: {err}")
    if args.values:
        return args.values
    if not sys.stdin.isatty():
        return sys.stdin.read().split()
    return None


def main(argv=None):
    """
    CLI для сортировки элементов (по умолчанию из stdin) с визуализацией.
    """
    parser = argparse.ArgumentParser(
        prog="my_sort", description="Плавная сортировка (smoothsort)")
    parser.add_argument("values", nargs="*",
                        help="элементы (если не заданы, читаются из stdin)")
    parser.add_argument("-r", "--reverse", action="store_true",
                        help="сортировать по невозрастанию")
    parser.add_argument("-k", "--key",
                        help="len, abs, lower, ... или 'lambda x: x[1]'")
    parser.add_argument("-c", "--cmp",
                        help="'lambda a, b: a < b' (True, если a меньше b)")
    parser.add_argument("-t", "--type", choices=["auto", "int", "float", "str"],
                        default="auto", help="тип элементов (по умолчанию auto)")
    parser.add_argument("-i", "--input", metavar="FILE",
                        help="читать элементы из файла (через пробелы/переводы строк)")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="записать результат в файл (один элемент на строку)")
    parser.add_argument("--random", type=int, metavar="N",
                        help="сгенерировать случайный список из N целых чисел")
    parser.add_argument("--min", type=int, default=0,
                        help="минимум для --random (по умолчанию 0)")
    parser.add_argument("--max", type=int, default=100,
                        help="максимум для --random (по умолчанию 100)")
    parser.add_argument("--seed", type=int,
                        help="seed генератора для воспроизводимости")
    parser.add_argument("-v", "--visualize", action="store_true",
                        help="показать анимацию сортировки (matplotlib)")
    parser.add_argument("-s", "--sound", action="store_true",
                        help="звуковое сопровождение визуализации")
    parser.add_argument("--delay", type=int, default=200,
                        help="задержка между кадрами, мс (по умолчанию 200)")
    args = parser.parse_args(argv)

    raw = _read_values(args, parser)
    if raw is None:
        parser.print_help()
        return

    key = _parse_key(args.key) if args.key else None
    cmp = _parse_lambda(args.cmp) if args.cmp else None
    data = _convert(raw, args.type, key)
    cmp = _parse_lambda(args.cmp) if args.cmp else None

    trace = [] if args.visualize else None
    result = _sort(data, args.reverse, key, cmp, trace)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write("\n".join(map(str, result)) + "\n")
        except OSError as err:
            parser.error(f"не удалось записать {args.output}: {err}")
    else:
        print(*result)

    if args.visualize and len(trace) > 1:
        _visualize(trace, result, args.delay, args.sound)


if __name__ == "__main__":
    main()

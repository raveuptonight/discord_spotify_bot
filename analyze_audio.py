"""librespot の生 PCM 出力を解析し、途切れ・グリッチを検出するスクリプト"""

import struct
import sys
import os

SAMPLE_RATE = 44100
CHANNELS = 2
BYTES_PER_SAMPLE = 2  # S16LE
FRAME_SIZE = CHANNELS * BYTES_PER_SAMPLE  # 4 bytes per frame


def analyze(path: str):
    file_size = os.path.getsize(path)
    total_frames = file_size // FRAME_SIZE
    duration = total_frames / SAMPLE_RATE

    print(f"ファイル: {path}")
    print(f"サイズ: {file_size:,} bytes")
    print(f"フレーム数: {total_frames:,}")
    print(f"推定時間: {duration:.2f} 秒")
    print()

    with open(path, "rb") as f:
        raw = f.read()

    # S16LE ステレオとしてデコード
    num_samples = len(raw) // BYTES_PER_SAMPLE
    samples = struct.unpack(f"<{num_samples}h", raw[: num_samples * BYTES_PER_SAMPLE])

    # --- 1. 無音区間の検出 ---
    silence_threshold = 50  # ±50 以下を無音とみなす
    silence_runs = []
    run_start = None
    for i in range(0, len(samples), CHANNELS):
        left = abs(samples[i])
        right = abs(samples[i + 1]) if i + 1 < len(samples) else 0
        is_silent = left < silence_threshold and right < silence_threshold
        frame_idx = i // CHANNELS
        if is_silent:
            if run_start is None:
                run_start = frame_idx
        else:
            if run_start is not None:
                run_len = frame_idx - run_start
                if run_len >= 100:  # 100 フレーム以上（~2.3ms）の無音のみ報告
                    silence_runs.append((run_start, run_len))
                run_start = None
    if run_start is not None:
        run_len = total_frames - run_start
        if run_len >= 100:
            silence_runs.append((run_start, run_len))

    print(f"=== 無音区間 (>= 100 フレーム / ~2.3ms) ===")
    if silence_runs:
        for start, length in silence_runs[:20]:
            t = start / SAMPLE_RATE
            dur_ms = length / SAMPLE_RATE * 1000
            print(f"  {t:.3f}s 付近: {dur_ms:.1f}ms ({length} frames)")
        if len(silence_runs) > 20:
            print(f"  ... 他 {len(silence_runs) - 20} 箇所")
        print(f"  合計: {len(silence_runs)} 箇所")
    else:
        print("  検出なし")
    print()

    # --- 2. 急激な振幅変化（不連続点）の検出 ---
    discontinuities = []
    jump_threshold = 20000  # サンプル間の差がこれを超えたら不連続
    for i in range(CHANNELS, len(samples) - CHANNELS, CHANNELS):
        for ch in range(CHANNELS):
            diff = abs(samples[i + ch] - samples[i + ch - CHANNELS])
            if diff > jump_threshold:
                frame_idx = i // CHANNELS
                discontinuities.append((frame_idx, ch, diff, samples[i + ch - CHANNELS], samples[i + ch]))
                break  # 1フレームにつき1回だけ報告

    print(f"=== 不連続点 (サンプル差 > {jump_threshold}) ===")
    if discontinuities:
        for frame_idx, ch, diff, prev, curr in discontinuities[:20]:
            t = frame_idx / SAMPLE_RATE
            ch_name = "L" if ch == 0 else "R"
            print(f"  {t:.3f}s [{ch_name}]: {prev} → {curr} (差: {diff})")
        if len(discontinuities) > 20:
            print(f"  ... 他 {len(discontinuities) - 20} 箇所")
        print(f"  合計: {len(discontinuities)} 箇所")
    else:
        print("  検出なし")
    print()

    # --- 3. 完全ゼロブロックの検出 ---
    block_size = 1024  # 1024 フレーム単位でチェック
    zero_blocks = []
    for i in range(0, len(samples) - block_size * CHANNELS, block_size * CHANNELS):
        block = samples[i : i + block_size * CHANNELS]
        if all(s == 0 for s in block):
            frame_idx = i // CHANNELS
            zero_blocks.append(frame_idx)

    print(f"=== 完全ゼロブロック ({block_size} フレーム単位) ===")
    if zero_blocks:
        # 連続するゼロブロックをまとめる
        groups = []
        g_start = zero_blocks[0]
        g_prev = zero_blocks[0]
        for zb in zero_blocks[1:]:
            if zb == g_prev + block_size:
                g_prev = zb
            else:
                groups.append((g_start, g_prev + block_size - g_start))
                g_start = zb
                g_prev = zb
        groups.append((g_start, g_prev + block_size - g_start))

        for start, length in groups[:20]:
            t = start / SAMPLE_RATE
            dur_ms = length / SAMPLE_RATE * 1000
            print(f"  {t:.3f}s 付近: {dur_ms:.1f}ms ({length} frames)")
        print(f"  合計: {len(groups)} 箇所")
    else:
        print("  検出なし")
    print()

    # --- 4. 全体統計 ---
    left_ch = samples[0::2]
    right_ch = samples[1::2]
    print(f"=== 全体統計 ===")
    print(f"  L ch: min={min(left_ch)}, max={max(left_ch)}, avg={sum(abs(s) for s in left_ch) / len(left_ch):.0f}")
    print(f"  R ch: min={min(right_ch)}, max={max(right_ch)}, avg={sum(abs(s) for s in right_ch) / len(right_ch):.0f}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/librespot_test.raw"
    if not os.path.exists(path):
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)
    analyze(path)

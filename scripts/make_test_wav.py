import wave, math, struct

OUT = "test_mono16k_pcm16_2s.wav"
sr = 16000
seconds = 2.0
freq = 440.0
amp = 0.2  # 0..1

n = int(sr * seconds)

with wave.open(OUT, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)  # PCM16
    w.setframerate(sr)

    frames = bytearray()
    for i in range(n):
        s = math.sin(2 * math.pi * freq * (i / sr))
        v = int(max(-1.0, min(1.0, s * amp)) * 32767)
        frames += struct.pack("<h", v)

    w.writeframes(frames)

print("Wrote", OUT, "frames=", n, "bytes=", len(frames))

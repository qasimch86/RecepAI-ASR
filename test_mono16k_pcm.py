import wave

with wave.open("test_mono16k_pcm16.wav", "rb") as w:
    print("Channels:", w.getnchannels())
    print("SampleRate:", w.getframerate())
    print("SampleWidth:", w.getsampwidth())
    print("Frames:", w.getnframes())

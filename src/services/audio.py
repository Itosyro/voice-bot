from io import BytesIO

from pydub import AudioSegment


def ogg_to_mp3(ogg_bytes: bytes) -> bytes:
    audio = AudioSegment.from_ogg(BytesIO(ogg_bytes))
    out = BytesIO()
    audio.export(out, format="mp3", bitrate="64k")
    return out.getvalue()

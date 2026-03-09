from openrelay.feishu_ws_proto import Frame, Header, decode_frame, encode_frame



def test_feishu_ws_proto_round_trip_frame() -> None:
    frame = Frame(
        seq_id=1,
        log_id=2,
        service=3,
        method=1,
        headers=[Header(key="type", value="event"), Header(key="message_id", value="m1")],
        payload_encoding="json",
        payload_type="application/json",
        payload=b'{"ok":true}',
        log_id_new="abc",
    )
    decoded = decode_frame(encode_frame(frame))
    headers = {header.key: header.value for header in decoded.headers}
    assert decoded.seq_id == 1
    assert decoded.log_id == 2
    assert decoded.service == 3
    assert decoded.method == 1
    assert headers["message_id"] == "m1"
    assert decoded.payload == b'{"ok":true}'
    assert decoded.log_id_new == "abc"

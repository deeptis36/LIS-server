import socket
import time


# ============================================================
# TEST CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 5002

SAMPLE_ID = "SAMP-33872"


# ============================================================
# ASTM CONTROL CHARACTERS
# ============================================================

ENQ = b"\x05"
ACK = b"\x06"
EOT = b"\x04"
STX = b"\x02"
ETX = b"\x03"
ETB = b"\x17"
CR = b"\x0D"
LF = b"\x0A"


# ============================================================
# CHECKSUM
# ============================================================

def calculate_checksum(data: bytes) -> bytes:
    """
    ASTM checksum:
    Sum all bytes from STX payload through ETX/ETB.
    Keep the lower 8 bits.
    Return two uppercase hexadecimal characters.
    """

    checksum = sum(data) & 0xFF

    return f"{checksum:02X}".encode("ascii")


# ============================================================
# RECEIVE ACK
# ============================================================

def wait_for_ack(sock):
    response = sock.recv(1)

    if response == ACK:
        print("[OK] ACK received")
        return True

    print(f"[ERROR] Expected ACK, received: {response!r}")
    return False


# ============================================================
# SEND ASTM FRAME
# ============================================================

def send_frame(sock, text, frame_number=1):

    payload = (
        str(frame_number)
        + text
    ).encode("ascii")

    # ASTM frame:
    #
    # STX
    # frame number + message
    # ETX
    # checksum
    # CR LF
    #

    checksum_data = (
        payload
        + ETX
    )

    checksum = calculate_checksum(checksum_data)

    frame = (
        STX
        + payload
        + ETX
        + checksum
        + CR
        + LF
    )

    print()
    print("[SEND FRAME]")
    print(text)

    sock.sendall(frame)

    return wait_for_ack(sock)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ERBA / MultiXL ASTM TEST SENDER")
    print("=" * 70)

    print(f"Target: {HOST}:{PORT}")
    print(f"Sample ID: {SAMPLE_ID}")

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(10)

        print()
        print("[INFO] Connecting...")

        sock.connect(
            (HOST, PORT)
        )

        print("[OK] TCP connection established.")

    except Exception as exc:

        print()
        print("[ERROR] Could not connect.")
        print(f"[ERROR] {exc}")

        return

    try:

        # ----------------------------------------------------
        # ENQ
        # ----------------------------------------------------

        print()
        print("[SEND] ENQ")

        sock.sendall(ENQ)

        if not wait_for_ack(sock):
            return

        # ----------------------------------------------------
        # ASTM MESSAGE
        # ----------------------------------------------------

        messages = [

            "H|\\^&|ERBA|EM200||||LIS",

            f"P|1|{SAMPLE_ID}||TARACHAN^TEST||",

            f"O|1|{SAMPLE_ID}||ALPU^ALP",

            "R|1|^^^ALPU|47|U/L|40-129|L||F",

            "R|2|^^^BIDD|0.0|mg/dl|0.0-1.2|N||F",

            "R|3|^^^CRE|0.9|mg/dl|0.6-1.3|N||F",

            "R|4|^^^UREA|32|mg/dl|15-45|N||F",

            "L|1|N",

        ]

        # ----------------------------------------------------
        # SEND FRAMES
        # ----------------------------------------------------

        frame_number = 1

        for message in messages:

            success = send_frame(
                sock,
                message,
                frame_number
            )

            if not success:
                print()
                print("[ERROR] Frame was not acknowledged.")
                return

            frame_number += 1

            time.sleep(0.2)

            # ASTM frame numbers cycle 1-7
            if frame_number > 7:
                frame_number = 0

        # ----------------------------------------------------
        # EOT
        # ----------------------------------------------------

        print()
        print("[SEND] EOT")

        sock.sendall(EOT)

        print()
        print("=" * 70)
        print("TEST MESSAGE SENT SUCCESSFULLY")
        print("=" * 70)

    except Exception as exc:

        print()
        print("[ERROR] Error while sending ASTM data.")
        print(f"[ERROR] {exc}")

    finally:

        sock.close()

        print()
        print("[INFO] TCP connection closed.")


if __name__ == "__main__":
    main()
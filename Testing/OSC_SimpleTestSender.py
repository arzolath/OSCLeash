"""Send a short grab/stretch/release sequence to an OSCLeash receiver."""
import argparse
import time

from pythonosc.udp_client import SimpleUDPClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9001,
                        help='Receiver UDP port printed by OSCLeash (default: 9001)')
    parser.add_argument('--leash', default='Leash', help='Physbone parameter name')
    parser.add_argument('--duration', type=float, default=5,
                        help='Seconds to hold the leash (default: 5)')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 < args.duration <= 300:
        parser.error('port must be 1..65535 and duration must be greater than 0 and at most 300 seconds')

    print(f'Sending {args.leash} forward movement to {args.host}:{args.port} for {args.duration:g}s')
    with SimpleUDPClient(args.host, args.port) as client:
        try:
            deadline = time.monotonic() + args.duration
            while time.monotonic() < deadline:
                for axis in ('Z+', 'Z-', 'X+', 'X-', 'Y+', 'Y-'):
                    client.send_message(f'/avatar/parameters/Leash_{axis}', 1.0 if axis == 'Z+' else 0.0)
                client.send_message(f'/avatar/parameters/{args.leash}_Stretch', 0.8)
                client.send_message(f'/avatar/parameters/{args.leash}_IsGrabbed', True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            for _ in range(2):
                client.send_message(f'/avatar/parameters/{args.leash}_IsGrabbed', False)
                client.send_message(f'/avatar/parameters/{args.leash}_Stretch', 0.0)
                time.sleep(0.05)
            print('Leash released')


if __name__ == '__main__':
    main()

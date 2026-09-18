"""Standalone simulated worker. JSONL input is engineering replay, not a live feed."""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading
from sqlalchemy import create_engine
from app.core.config import Settings
from app.runtime.paper import PaperRuntime


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, required=True, help='dedicated SQLite simulation database')
    p.add_argument('--commission', type=float, default=0)
    p.add_argument('--slippage-bps', type=float, default=5)
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--feed', type=Path, required=True, help='append-only JSONL simulation events')
    run.add_argument('--enable-paper', action='store_true', help='explicitly transition OFF to PAPER')
    run.add_argument('--once', action='store_true', help='process current complete input then exit')
    run.add_argument('--interval', type=float, default=2)
    sub.add_parser('status')
    halt = sub.add_parser('halt')
    halt.add_argument('--reason', default='operator request')
    reset = sub.add_parser('reset')
    reset.add_argument('--confirm', action='store_true', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    engine = None
    try:
        # A paper worker is explicitly selected by this entry point. Never
        # override an unsafe LIVE flag/mode inherited from the environment.
        cfg = Settings(AUTO_EXECUTION=True, AUTONOMY_LEVEL=2)
        args.database.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f'sqlite:///{args.database.resolve()}', connect_args={'timeout': 10})
        rt = PaperRuntime(engine, cfg, commission=args.commission, slippage_bps=args.slippage_bps)
        if args.command == 'status':
            print(json.dumps(rt.status()), flush=True)
            return 0
        if args.command == 'halt':
            rt.halt(args.reason)
            print(json.dumps(rt.status()), flush=True)
            return 0
        if args.command == 'reset':
            rt.reset()
            print(json.dumps({'status': 'off', 'simulated': True}), flush=True)
            return 0
        if not 0.05 <= args.interval <= 30:
            raise ValueError('interval must be between 0.05 and 30 seconds')
        if args.enable_paper:
            rt.enable()
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        # Cursor is only an optimization. Persisted event IDs deduplicate after
        # process restart. File truncation/replacement is never silently accepted.
        offset = 0
        prefix = b''
        while not stop.is_set():
            content = args.feed.read_bytes()
            if not content.startswith(prefix):
                raise ValueError('simulation feed was modified or truncated')
            lines = content[offset:].splitlines(keepends=True)
            for raw in lines:
                if not raw.endswith(b'\n') and not args.once:
                    break  # writer has not completed the next event yet
                if stop.is_set():
                    break
                if raw.strip():
                    result = rt.process(json.loads(raw))
                    print(json.dumps(result), flush=True)
                    if result.get('status') == 'halted' or result.get('reason') == 'halted':
                        return 2
                offset += len(raw)
            prefix = content[:offset]
            rt.pulse()
            if args.once:
                return 0
            stop.wait(args.interval)
        return 0
    except Exception as exc:
        # A failed atomic tick leaves the last committed simulated state intact.
        # Halt separately so supervisors cannot restart into automatic trading.
        if engine is not None and 'rt' in locals():
            try:
                rt.halt(f'paper worker failure: {type(exc).__name__}')
            except Exception:
                pass  # database unavailable: process stops; no broker is reachable
        print(json.dumps({'status': 'failed', 'simulated': True, 'error': str(exc)}), file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())

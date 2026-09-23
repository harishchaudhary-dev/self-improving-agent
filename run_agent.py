"""Chat with the scheduling agent. Try:
  I'm Alice Rao, DOB 1990-04-12, I'd like to book a general checkup.
"""
import argparse
from src.agent import Agent, MockBackend

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    args = ap.parse_args()

    if args.mode == "real":
        from src.agent import AnthropicBackend
        backend = AnthropicBackend()
    else:
        backend = MockBackend()

    agent = Agent(backend=backend)
    print("Clara (scheduling assistant) -- type 'quit' to exit.\n")
    while True:
        msg = input("You: ").strip()
        if msg.lower() in ("quit", "exit"):
            break
        reply, tool_log = agent.user_turn(msg)
        if tool_log:
            for c in tool_log:
                print(f"   [tool] {c['name']}({c['args']}) -> {c['result']}")
        print(f"Clara: {reply}\n")

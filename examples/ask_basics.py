"""Use inv.ask + inv.kb to ask a grounded question over your KB and runs.

    export INVARIANCE_API_KEY=inv_live_...
    python examples/ask_basics.py

What this shows:
- write a KB page (`inv.kb.create_page`)
- send a question through the server-side agent loop (`inv.ask.send`)
- inspect the cited sources in the response

The /v1/ask endpoint runs a turn-based agent on the server with KB +
run-context tools enabled, so the response includes citations like
[[wiki:auth-flow]] (KB page) and [run:r_…] (run reference).
"""

from invariance import Invariance


def main() -> None:
    inv = Invariance()  # reads INVARIANCE_API_KEY

    page = inv.kb.create_page(
        path="wiki:refund-policy",
        title="Refund policy",
        body=(
            "Refunds over $1,000 require a manager review. "
            "Refunds for orders older than 90 days are denied by default."
        ),
    )
    print(f"wrote KB page {page.get('path')}")

    reply = inv.ask.send("When does a refund need manager review?")
    print("---")
    print(reply.get("final_text", "<no text>"))

    citations = reply.get("citations") or []
    if citations:
        print("---")
        print(f"{len(citations)} citation(s):")
        for c in citations[:5]:
            print(f"  - {c}")


if __name__ == "__main__":
    main()

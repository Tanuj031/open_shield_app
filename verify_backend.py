import os
import json
from app_core import analyze_contract_text

# Demo Indian employment contract with obvious risky clauses and hidden penalties
MOCK_CONTRACT = """
EMPLOYMENT AGREEMENT

This Employment Agreement ("Agreement") is entered into on this 1st day of July, 2026, by and between:
1. Shield Technologies Private Limited, a company incorporated under the Companies Act, 2013, having its registered office at Bengaluru, Karnataka (hereinafter "Company"); and
2. Rohan Sharma, residing at Mumbai, Maharashtra (hereinafter "Employee").

TERMS AND CONDITIONS:

1. Term and Position: The Employee shall serve as a Senior Software Engineer starting July 1, 2026.

2. Unilateral Fees and Late Payment Penalties: If the Employee fails to report to office by 9:00 AM on any working day, the Company reserves the right to levy a daily administrative penalty of INR 5,000, which will be deducted directly from the Employee's monthly salary. Furthermore, if the Employee terminates this agreement without serving the required notice period, the Employee shall pay liquidated damages of INR 10,00,000 as a penalty, which the parties agree is a genuine pre-estimate of loss.

3. Non-Compete: The Employee agrees that for a period of two (2) years following the termination of employment, the Employee shall not work for any competitor of the Company anywhere in India. The Employee acknowledges that this restriction is reasonable and necessary for the protection of the Company's business.

4. Termination and Indemnity: The Company may terminate this Agreement at any time without notice and without cause. If the Employee is terminated for cause, the Employee shall indemnify the Company for any lost profits, indirect damages, and lawyer fees up to an unlimited amount. The Employee may only terminate this agreement by giving 6 months' written notice.

5. Governing Law and Jurisdiction: This Agreement shall be governed by and construed in accordance with the laws of India. Any dispute arising out of or in connection with this Agreement shall be subject to the exclusive jurisdiction of the courts of Mumbai.
"""


def test_analysis():
    print("=" * 60)
    print("  PocketLawAI — Backend Verification Test")
    print("=" * 60)

    # Check for GEMINI_API_KEY
    if not os.environ.get("GEMINI_API_KEY"):
        print("\n❌ Error: GEMINI_API_KEY environment variable is not set.")
        print("   Windows PowerShell:     $env:GEMINI_API_KEY='your_key'")
        print("   Windows Command Prompt: set GEMINI_API_KEY=your_key")
        return

    print("\n🔍 Analyzing mock contract using Gemini...\n")
    try:
        result = analyze_contract_text(MOCK_CONTRACT)

        # 1. Overall Risk Score
        print(f"📊 Overall Risk Score: {result.overall_risk_score}")
        print(f"   → {result.overall_risk_explanation}")

        # 2. Summary
        print(f"\n📝 Plain-English Summary:\n   {result.summary}")

        # 3. Governing Law
        print(f"\n⚖️ Governing Law:\n   {result.governing_law_notes}")

        # 4. Clauses
        print(f"\n📋 Clauses Analyzed: {len(result.clauses)}")
        for c in result.clauses:
            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(c.risk_level.lower(), "⚪")
            flag = " 🚩" if c.is_red_flag else ""
            print(f"\n   {risk_icon} Clause {c.clause_number}: {c.clause_title} [{c.risk_level}]{flag}")
            print(f"     Reason: {c.risk_reason}")
            if c.is_red_flag and c.red_flag_type:
                print(f"     Red flag type: {c.red_flag_type}")
            if c.negotiation_suggestion:
                print(f"     💡 Negotiate: {c.negotiation_suggestion}")

        # 5. Red Flags
        print(f"\n🚩 Red Flags: {len(result.red_flags)}")
        for rf in result.red_flags:
            print(f"   🔴 {rf.pattern_name} (Severity: {rf.severity})")
            print(f"     Clause: {rf.clause_reference}")
            print(f"     {rf.explanation}")

        # 6. Hidden Penalties
        print(f"\n💰 Hidden Penalties: {len(result.hidden_penalties)}")
        for hp in result.hidden_penalties:
            print(f"   ⚠️ {hp.penalty_title} (Severity: {hp.severity})")
            print(f"     Impact: {hp.implication}")
            print(f"     Mitigation: {hp.mitigation}")

        # 7. Negotiation Points
        print(f"\n🤝 Negotiation Points: {len(result.negotiation_points)}")
        for np_ in result.negotiation_points:
            print(f"   #{np_.priority}: {np_.point}")
            print(f"     Related to: {np_.related_clause}")

        print("\n" + "=" * 60)
        print("  ✅ Test passed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")


if __name__ == "__main__":
    test_analysis()

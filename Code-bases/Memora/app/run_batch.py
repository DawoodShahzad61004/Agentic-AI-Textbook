"""
run_batch.py — Automated batch tester for the Agentic RAG system.

Usage (run from inside the app/ directory):
    python run_batch.py --batch 1
    python run_batch.py --batch 3
    python run_batch.py --list          # show all available batches

Each batch runs its questions sequentially against the live agent, feeds
special commands (bad / stats / learn) at the right moments, and writes
everything — every print, every retrieved chunk, every LLM response — to
a timestamped log file in  ../data/test_logs/.

The script drives agent_query.main() by monkey-patching sys.stdin so the
agent's  input("Your question: ")  calls read from our scripted list
instead of the keyboard.  stdout is tee'd to both the terminal and the log
file simultaneously so you can watch progress live.
"""

import sys
import os
import io
import logging
import argparse
import textwrap
from datetime import datetime
from pathlib import Path

from logger_config import setup_logging

logger = logging.getLogger(__name__)


# ── Tee: write to both terminal and a file at the same time ──────────────────

class _Tee(io.TextIOBase):
    """Wrap a real stream so every write goes to both that stream and a file."""

    def __init__(self, real_stream, log_file):
        self._real = real_stream
        self._log  = log_file

    def write(self, data):
        self._real.write(data)
        self._real.flush()
        self._log.write(data)
        self._log.flush()
        return len(data)

    def flush(self):
        self._real.flush()
        self._log.flush()

    # Make sure print() / logging that checks isatty() don't crash
    def isatty(self):
        return False

    # Passthrough so things like colorama don't blow up
    def fileno(self):
        return self._real.fileno()


# ── Scripted stdin ────────────────────────────────────────────────────────────

class _ScriptedStdin:
    """
    Replaces sys.stdin.  Every call to input() in agent_query pulls the next
    entry from our script list.

    A script entry is one of:
        str   — fed straight to input() as the typed text
        dict  — {"type": "bad", "feedback": "..."}  triggers the two-step
                bad-flag flow (first input returns "bad", second returns the
                feedback string)

    Between entries we print a visible banner so the log is easy to navigate.
    """

    def __init__(self, entries: list, out_stream):
        self._entries  = list(entries)
        self._pos      = 0
        self._out      = out_stream
        # When we encounter a "bad" dict we need to emit two inputs:
        # 1. "bad"  2. the feedback.  This queue handles the second one.
        self._pending: list[str] = []

    def readline(self):
        return self._next() + "\n"

    def _next(self) -> str:
        # Drain any pending (e.g., feedback line after "bad")
        if self._pending:
            value = self._pending.pop(0)
            self._out.write(f"{value}\n")
            self._out.flush()
            return value

        if self._pos >= len(self._entries):
            # No more entries — send quit so the agent loop exits cleanly
            self._out.write("quit\n")
            self._out.flush()
            return "quit"

        entry = self._entries[self._pos]
        self._pos += 1

        # ── Special command dict ──────────────────────────────────────────────
        if isinstance(entry, dict):
            cmd  = entry.get("type", "bad")
            fb   = entry.get("feedback", "")
            note = entry.get("_note", "")

            banner = f"\n{'─'*70}\n  ▶ SCRIPT COMMAND: {cmd.upper()}"
            if note:
                banner += f"  [{note}]"
            banner += f"\n{'─'*70}\n"
            self._out.write(banner)
            self._out.flush()

            # Queue the feedback so the next input() call returns it
            self._pending.append(fb)
            return cmd

        # ── Regular question string ───────────────────────────────────────────
        banner = (
            f"\n{'═'*70}\n"
            f"  ▶ QUESTION {self._pos}/{len(self._entries)}: {entry}\n"
            f"{'═'*70}\n"
        )
        self._out.write(banner)
        self._out.flush()
        return entry


# ── Batch definitions ─────────────────────────────────────────────────────────
#
# Each batch is a dict:
#   name        : short label used in the log filename
#   description : one-liner shown when --list is used
#   questions   : ordered list of str | dict entries fed to _ScriptedStdin
#
# For "bad" commands use:
#   {"type": "bad", "feedback": "...", "_note": "optional label for log"}
#
# For "stats" or "learn" commands use:
#   {"type": "stats", "_note": "..."}
#   {"type": "learn", "_note": "..."}
#   (feedback key is ignored for stats/learn)
# ─────────────────────────────────────────────────────────────────────────────

BATCHES: dict[int, dict] = {

    # ── 1 ──────────────────────────────────────────────────────────────────────
    1: {
        "name": "asd_disambiguation_thumbdown",
        "description": "ASD disambiguation + thumbdown context switch (Q1–Q9)",
        "questions": [
            "What is ASD and what are its main characteristics?",
            "How is ASD diagnosed in children under 3 years old?",
            "What comorbid conditions are commonly found alongside ASD?",
            "Can ASD be caused by vaccines?",
            "What therapies are recommended for someone with ASD?",
            "Does ASD affect males and females equally?",
            {
                "type": "bad",
                "feedback": (
                    "I was actually asking about Adjustable Speed Drives, not autism. "
                    "All your answers were about the wrong topic."
                ),
                "_note": "Q7 — context switch thumbdown",
            },
            "What is ASD and what are its main characteristics?",
            "How does an ASD control the speed of an electric motor?",
        ],
    },

    # ── 2 ──────────────────────────────────────────────────────────────────────
    2: {
        "name": "adjustable_speed_drive_deep_dive",
        "description": "Adjustable Speed Drive deep dive + pivot back to autism (Q10–Q18)",
        "questions": [
            "What is the working principle of an Adjustable Speed Drive?",
            "What are the different types of Adjustable Speed Drives and when would you use each one?",
            "What causes harmonic distortion in an Adjustable Speed Drive and why is it a problem?",
            (
                "What would happen if an Adjustable Speed Drive was used with an older motor "
                "not designed for variable frequency operation?"
            ),
            "How do regenerative Adjustable Speed Drives recover energy and where are they used?",
            "What is the future of Adjustable Speed Drives in the context of AI and IoT?",
            "What ASD components are responsible for protecting the motor during faults?",
            "Now I want to go back to the medical topic — what are the early red flags for autism in infants?",
            "At what age should a child first be screened specifically for autism and what tool is used?",
        ],
    },

    # ── 3 ──────────────────────────────────────────────────────────────────────
    3: {
        "name": "zero_chunk_situations",
        "description": "Questions designed to produce zero retrieved chunks (Q19–Q24)",
        "questions": [
            (
                "What is the recommended dosage of risperidone for a 7-year-old child "
                "with autism and epilepsy?"
            ),
            "Which specific brand of Variable Frequency Drive is best for a 75 kW pump application?",
            "What are the ICD-11 diagnostic codes for Autism Spectrum Disorder?",
            "What did the 2023 CDC ADDM report say about ASD prevalence?",
            "Who manufactures the most widely used Adjustable Speed Drives in Europe?",
            {
                "type": "bad",
                "feedback": (
                    "The system said it had no information but I expected at least a partial "
                    "answer from what is in the knowledge base."
                ),
                "_note": "Q24 — thumbdown on a null-result answer",
            },
        ],
    },

    # ── 4 ──────────────────────────────────────────────────────────────────────
    4: {
        "name": "multi_retrieval_multi_source",
        "description": "Questions requiring multiple retrieval passes across sources (Q25–Q30)",
        "questions": [
            (
                "Compare the social communication deficits described in the DSM-5 criteria "
                "with the communication challenges listed in the patient management handbook "
                "and the ASD information file."
            ),
            (
                "What does the research say about the relationship between parental age and ASD risk, "
                "and does the patient dataset support this with its data on parental ages?"
            ),
            (
                "Across all the materials available, what sensory-related guidance is given "
                "for managing ASD patients?"
            ),
            (
                "What environmental and prenatal risk factors for ASD are described, and are there "
                "any fields in the patient dataset that capture these factors?"
            ),
            (
                "Describe everything the knowledge base says about epilepsy in ASD patients — "
                "from prevalence statistics to clinical management to which patients in the "
                "dataset have it."
            ),
            (
                "What does the knowledge base say about the energy efficiency benefits of "
                "Adjustable Speed Drives in HVAC systems, and separately, how do the "
                "energy-efficiency arguments compare to the cost concerns raised in the "
                "limitations section?"
            ),
        ],
    },

    # ── 5 ──────────────────────────────────────────────────────────────────────
    5: {
        "name": "hallucination_risk_partial_kb",
        "description": "Topics partially in the KB — high hallucination risk (Q31–Q37)",
        "questions": [
            "What is the prognosis for a child diagnosed with severe ASD at age 2?",
            (
                "Does the knowledge base say anything about whether ASD can be detected "
                "prenatally using genetic testing?"
            ),
            (
                "What is the relationship between ASD severity and IQ, based on what is "
                "in the knowledge base?"
            ),
            (
                "Can an Adjustable Speed Drive be used with a single-phase household "
                "power supply?"
            ),
            (
                "What is the difference between ASD severity levels mild, moderate, and severe "
                "as defined in the knowledge base?"
            ),
            (
                "According to the patient dataset, do female patients get diagnosed later "
                "than male patients on average?"
            ),
            (
                "Does the knowledge base say anything about the cost-effectiveness of ABA "
                "therapy for children with severe ASD?"
            ),
        ],
    },

    # ── 6 ──────────────────────────────────────────────────────────────────────
    6: {
        "name": "dataset_analytical",
        "description": "Dataset-specific analytical questions (Q38–Q44)",
        "questions": [
            "How many patients in the dataset have both ADHD and anxiety as comorbidities?",
            (
                "Are there any patients in the dataset who have been diagnosed with ASD "
                "but have no recorded severity level?"
            ),
            "Which patients in the dataset have an ADOS score above 15?",
            (
                "What medications are recorded in the patient dataset and which patients "
                "are on each?"
            ),
            (
                "Is there a pattern in the dataset between low socioeconomic status and "
                "later age at diagnosis?"
            ),
            (
                "How many patients in the dataset have a family history of ASD, and do they "
                "tend to have more severe presentations?"
            ),
            (
                "Which school setting is most common among patients with severe ASD "
                "in the dataset?"
            ),
        ],
    },

    # ── 7 ──────────────────────────────────────────────────────────────────────
    7: {
        "name": "disparity_gender_race",
        "description": "Gender and race disparity questions from the essay (Q45–Q49)",
        "questions": [
            (
                "Why are girls with autism more likely to be misdiagnosed with anxiety "
                "or depression instead of receiving an ASD diagnosis?"
            ),
            (
                "What does the research say about the intersection of being both a girl "
                "and from a minority racial group when it comes to ASD diagnosis?"
            ),
            (
                "Did Black and Hispanic children historically receive more or fewer ASD "
                "diagnoses than White children, and has that changed recently?"
            ),
            (
                "What does masking mean in the context of autism, and which population "
                "is most affected by it?"
            ),
            (
                "The disparities essay talks about structural barriers. Does the patient "
                "dataset show any evidence of these barriers, for example in the "
                "socioeconomic or school setting data?"
            ),
        ],
    },

    # ── 8 ──────────────────────────────────────────────────────────────────────
    8: {
        "name": "sustained_acronym_trap",
        "description": "Sustained ASD acronym trap with domain-hint queries (Q50–Q56)",
        "questions": [
            "What does ASD stand for in an industrial engineering context?",
            "What does ASD stand for in a medical or pediatric context?",
            "I am an HVAC engineer. What should I know about ASD?",
            "I am a pediatrician. What should I know about ASD?",
            (
                "What are the main challenges associated with ASD that could affect "
                "equipment performance?"
            ),
            (
                "What are the main challenges associated with ASD that could affect "
                "a child's development?"
            ),
            {
                "type": "bad",
                "feedback": (
                    "For the equipment performance question, you answered about autism "
                    "instead of the industrial device. The question was clearly about "
                    "equipment, not children."
                ),
                "_note": "Q56 — wrong domain picked for equipment question",
            },
        ],
    },

    # ── 9 ──────────────────────────────────────────────────────────────────────
    9: {
        "name": "large_chunk_load",
        "description": "Broad queries expected to produce a large number of chunks (Q57–Q60)",
        "questions": [
            (
                "Give me a complete overview of Autism Spectrum Disorder — its definition, "
                "causes, prevalence, diagnosis process, treatment options, and associated "
                "disparities."
            ),
            (
                "Tell me everything the knowledge base contains about sensory processing "
                "in ASD — from clinical criteria, to patient characteristics, to management "
                "strategies, to how it affects diagnosis."
            ),
            (
                "Summarize all the risk factors for ASD — genetic, environmental, prenatal, "
                "and demographic — drawing from everything in the knowledge base."
            ),
            (
                "What does the knowledge base say about the advantages, limitations, "
                "applications, and future of Adjustable Speed Drives?"
            ),
        ],
    },

    # ── 10 ─────────────────────────────────────────────────────────────────────
    10: {
        "name": "inference_and_reasoning",
        "description": "Inference and applied reasoning traps (Q61–Q67)",
        "questions": [
            (
                "Patient P013 in the dataset is a 13-year-old female diagnosed at 72 months "
                "with mild ASD, high socioeconomic status, and no therapies recorded. Based "
                "on the knowledge base, what factors might explain her late diagnosis and "
                "absence of therapy?"
            ),
            (
                "The dataset shows that all patients with severe ASD and epilepsy are male. "
                "Is this consistent with what the scientific literature in the knowledge base says?"
            ),
            (
                "An engineer is considering installing an Adjustable Speed Drive on a "
                "1990s-era motor. What risks does the knowledge base warn about?"
            ),
            (
                "A hospital wants to reduce sensory stimulation for ASD patients during "
                "procedures. Based only on what is in the knowledge base, what specific "
                "environmental changes are recommended?"
            ),
            (
                "Why might a child with Asperger's disorder under DSM-IV not qualify "
                "for an ASD diagnosis under DSM-5?"
            ),
            (
                "The knowledge base mentions that the true male-to-female ratio in ASD may "
                "be closer to 3:1 than the older 4:1 figure. What does this imply about "
                "historical diagnosis patterns, according to the documents?"
            ),
            (
                "If an Adjustable Speed Drive is installed in a water treatment plant and "
                "starts causing interference with nearby sensors, what does the knowledge "
                "base say is likely causing this and how could it be addressed?"
            ),
        ],
    },

    # ── 11 ─────────────────────────────────────────────────────────────────────
    11: {
        "name": "contradictions_and_gaps",
        "description": "Contradictions, gaps, and knowledge-boundary testing (Q68–Q73)",
        "questions": [
            (
                "The knowledge base mentions that ASD prevalence appeared to stabilize between "
                "2014 and 2016, but also that a 2022 surveillance report found higher prevalence "
                "in minority groups. Are these findings contradictory?"
            ),
            (
                "Does the knowledge base say whether folic acid supplementation can prevent ASD?"
            ),
            "Is intellectual disability always present in ASD?",
            (
                "The dataset has patients with ASD_Diagnosis=No but no ASD_Severity recorded. "
                "What does this mean?"
            ),
            (
                "Does the knowledge base say that Adjustable Speed Drives are safe to use "
                "near sensitive medical equipment?"
            ),
            (
                "Is there any evidence in the knowledge base that early diagnosis of ASD "
                "leads to better outcomes?"
            ),
        ],
    },

    # ── 12 ─────────────────────────────────────────────────────────────────────
    12: {
        "name": "self_learning_pipeline",
        "description": "Self-learning and memory pipeline tests (Q74–Q80)",
        "questions": [
            "What is ASD and how does it affect children's social development?",
            {"type": "stats", "_note": "Q75 — baseline stats before learning"},
            "What screening tools are used for ASD in preschool-aged children?",
            "What are the energy savings benefits of using Variable Frequency Drives in pump systems?",
            {"type": "learn", "_note": "Q78 — force distillation"},
            {"type": "stats", "_note": "Q79 — verify learned QA count increased"},
            "What screening tools are used for ASD in preschool-aged children?",
        ],
    },

    # ── 13 ─────────────────────────────────────────────────────────────────────
    13: {
        "name": "multi_turn_thumbdown_refinement",
        "description": "Multi-turn thumbdown refinement — steer retrieval with feedback (Q81–Q86)",
        "questions": [
            "What are the components of a comprehensive ASD evaluation?",
            {
                "type": "bad",
                "feedback": (
                    "You listed the components but did not mention anything about the genetic "
                    "testing guidelines from ACMGG or chromosomal microarray."
                ),
                "_note": "Q82 — targeted feedback to steer toward genetic testing subsection",
            },
            "What are the components of a comprehensive ASD evaluation?",
            "What are the safety features built into an Adjustable Speed Drive?",
            {
                "type": "bad",
                "feedback": (
                    "The answer was too generic. I wanted to know specifically about the "
                    "control unit's fault detection role and how it initiates protective actions."
                ),
                "_note": "Q85 — steer toward control unit subsection",
            },
            "What are the safety features built into an Adjustable Speed Drive?",
        ],
    },

    # ── 14 ─────────────────────────────────────────────────────────────────────
    14: {
        "name": "quality_checker_and_grounding",
        "description": "Quality checker stress tests and answer grounding (Q87–Q90)",
        "questions": [
            "Give me a 10-word answer: what causes ASD?",
            (
                "I already know the basics. Just tell me the one most important thing about "
                "Adjustable Speed Drives that most engineers overlook."
            ),
            "List every single fact from all documents about ASD in one answer.",
            (
                "According to the knowledge base, which is more effective for ASD — "
                "ABA therapy or speech therapy?"
            ),
        ],
    },

    # ── 15 ─────────────────────────────────────────────────────────────────────
    15: {
        "name": "final_mixed_edge_cases",
        "description": "Final mixed and edge-case scenarios (Q91–Q100)",
        "questions": [
            (
                "I work in an industrial plant and my colleague keeps talking about ASD issues "
                "causing production slowdowns. What might they mean?"
            ),
            (
                "My child's pediatrician mentioned ASD issues at their last checkup. "
                "What should I be asking about?"
            ),
            (
                "Is there anything in the knowledge base that applies to both ASD meaning autism "
                "and ASD meaning Adjustable Speed Drive at the same time?"
            ),
            (
                "The handbook says to remain calm during sensory overload. How should a clinician "
                "actually do that in practice?"
            ),
            (
                "What percentage of energy can a facility realistically expect to save by "
                "installing Adjustable Speed Drives on all its fans and pumps?"
            ),
            "Does the patient dataset contain any patients who have no comorbidities at all?",
            (
                "What does the knowledge base say about the role of parental age in ASD — "
                "and does the patient dataset reflect this with any notable parental age data?"
            ),
            (
                "Based on everything in the knowledge base, write a brief summary a "
                "non-specialist could read to understand what ASD is, how it is identified, "
                "and how it is managed."
            ),
            {
                "type": "bad",
                "feedback": (
                    "Good summary but it said nothing about the racial and gender disparities "
                    "in diagnosis, which I consider essential context."
                ),
                "_note": "Q99 — final thumbdown to add disparities content",
            },
            (
                "Based on everything in the knowledge base, write a brief summary a "
                "non-specialist could read to understand what ASD is, how it is identified, "
                "and how it is managed."
            ),
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_dir() -> Path:
    p = Path(__file__).parent / "run_logs" / "test_batch_logs"
    p = p.resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log_path(batch_id: int, batch_name: str) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"batch{batch_id:02d}_{batch_name}_{ts}.txt"
    return _log_dir() / name


def _list_batches() -> None:
    print("\nAvailable batches:\n")
    for bid, b in sorted(BATCHES.items()):
        n_q = len(b["questions"])
        print(f"  {bid:>2}.  {b['name']}")
        print(f"        {b['description']}")
        print(f"        {n_q} script entries\n")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_batch(batch_id: int) -> None:
    if batch_id not in BATCHES:
        logger.error(f"Batch {batch_id} does not exist. Use --list to see options.")
        sys.exit(1)

    batch    = BATCHES[batch_id]
    log_path = _log_path(batch_id, batch["name"])

    print(f"\n{'═'*70}")
    print(f"  BATCH {batch_id}: {batch['name']}")
    print(f"  {batch['description']}")
    print(f"  Log → {log_path}")
    print(f"{'═'*70}\n")

    with log_path.open("w", encoding="utf-8") as log_file:

        # Write a header to the log
        header = (
            f"{'═'*70}\n"
            f"  RAG BATCH TEST RUN\n"
            f"  Batch   : {batch_id} — {batch['name']}\n"
            f"  Desc    : {batch['description']}\n"
            f"  Started : {datetime.now().isoformat()}\n"
            f"{'═'*70}\n\n"
        )
        log_file.write(header)
        log_file.flush()

        # Tee stdout and stderr to the log file
        tee_out = _Tee(sys.__stdout__, log_file)
        tee_err = _Tee(sys.__stderr__, log_file)
        sys.stdout = tee_out
        sys.stderr = tee_err

        # Set up scripted stdin
        scripted = _ScriptedStdin(batch["questions"], tee_out)
        original_input = __builtins__.__dict__.get("input") if isinstance(__builtins__, dict) else getattr(__builtins__, "input", None)

        def _patched_input(prompt=""):
            # Print the prompt (agent prints "Your question: ")
            sys.stdout.write(prompt)
            sys.stdout.flush()
            return scripted.readline().rstrip("\n")

        # Patch builtins.input so agent_query's input() calls use our script
        import builtins
        builtins.input = _patched_input

        try:
            # Import and run the agent — it will consume our scripted inputs
            # We need to add the project app/ directory to the path
            app_dir = Path(__file__).parent.parent / "app"
            if not app_dir.exists():
                # Fallback: look for agent_query.py next to this script
                app_dir = Path(__file__).parent
            if str(app_dir) not in sys.path:
                sys.path.insert(0, str(app_dir))

            import agent_query
            agent_query.main()

        except SystemExit:
            pass
        except KeyboardInterrupt:
            logger.warning("[run_batch] Interrupted by user")
        except Exception:
            logger.exception("[run_batch] Unexpected error")
        finally:
            # Restore builtins.input
            builtins.input = original_input
            # Restore stdout/stderr
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

    # Footer printed to real stdout after restoration
    print(f"\n{'═'*70}")
    print(f"  BATCH {batch_id} COMPLETE")
    print(f"  Log saved → {log_path}")
    print(f"{'═'*70}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Automated batch tester for the Agentic RAG system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python run_batch.py --list
              python run_batch.py --batch 1
              python run_batch.py --batch 9
        """),
    )
    parser.add_argument(
        "--batch", "-b",
        type=int,
        metavar="N",
        help="Batch number to run (use --list to see all)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available batches and exit",
    )
    args = parser.parse_args()

    if args.list:
        _list_batches()
        return

    if args.batch is None:
        parser.print_help()
        logger.error("Provide --batch N or --list")
        sys.exit(1)

    run_batch(args.batch)


if __name__ == "__main__":
    main()

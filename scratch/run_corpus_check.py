import sys
sys.path.insert(0, '.')
from pdf_analyzer.corpus_check import CorpusCheckEngine, print_corpus_check_report, corpus_check_exit_code
engine = CorpusCheckEngine()
report = engine.run_corpus_check()
print_corpus_check_report(report)
code = corpus_check_exit_code(report)
print(f'Exit code: {code}')


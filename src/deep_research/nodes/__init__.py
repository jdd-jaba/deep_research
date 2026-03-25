"""LangGraph node implementations."""

from importlib import import_module

# Import nodes from numbered files
_module_01 = import_module('.01_create_subtopics', 'deep_research.nodes')
_module_02 = import_module('.02_load_next_subtopic', 'deep_research.nodes')
_module_03 = import_module('.03_search_web', 'deep_research.nodes')
_module_04 = import_module('.04_fetch_page_content', 'deep_research.nodes')
_module_05 = import_module('.05_summarize_sources', 'deep_research.nodes')
_module_06 = import_module('.06_evaluate_coverage', 'deep_research.nodes')
_module_07 = import_module('.07_generate_similar_question_if_necessary', 'deep_research.nodes')
_module_08 = import_module('.08_write_section', 'deep_research.nodes')
_module_09 = import_module('.09_finalize_report', 'deep_research.nodes')

# Extract functions (keeping original function names for compatibility)
plan_research = _module_01.plan_research
advance_plan = _module_02.advance_plan
web_research = _module_03.web_research
fetch_pages = _module_04.fetch_pages
summarize_sources = _module_05.summarize_sources
reflect_on_summary = _module_06.reflect_on_summary
generate_similar_questions = _module_07.generate_similar_questions
write_section = _module_08.write_section
finalize_report = _module_09.finalize_report

__all__ = [
    "plan_research",
    "advance_plan",
    "web_research",
    "fetch_pages",
    "summarize_sources",
    "reflect_on_summary",
    "generate_similar_questions",
    "write_section",
    "finalize_report",
]

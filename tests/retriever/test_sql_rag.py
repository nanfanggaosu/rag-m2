from rag.src_rag.llm.fake import FakeLlm
from rag.src_rag.retriever.sql_rag import SqlRag, build_prompt

GOOD = "SELECT name FROM factions WHERE name = 'Orks'"


def _reply(sql):
    return {"reasoning": "test", "sql": sql}


def test_first_good_query_is_returned():
    llm = FakeLlm([_reply(GOOD)])
    rag = SqlRag(llm)
    out = rag("Which faction are Boyz from?")
    assert out.error is None
    assert out.rows == [{"name": "Orks"}]
    assert out.sql == GOOD
    assert len(llm.prompts) == 1 and len(rag.last_attempts) == 1


def test_prompt_contains_rules_schema_values_examples_and_question():
    prompt = build_prompt("How many points do Boyz cost?", max_rows=50)
    assert "Every column is TEXT" in prompt
    assert "TABLE datasheets_models_cost" in prompt
    assert "datasheets.name = 'Boyz'" in prompt
    assert "Q: How many points does an Intercessor Squad cost?" in prompt
    assert prompt.endswith("QUESTION: How many points do Boyz cost?")


def test_sql_error_is_fed_back_and_retried():
    llm = FakeLlm([_reply("SELECT nme FROM factions"), _reply(GOOD)])
    rag = SqlRag(llm)
    out = rag("Which faction are Boyz from?")
    assert out.error is None and out.sql == GOOD
    assert "no such column: nme" in llm.prompts[1]
    assert "SQL: SELECT nme FROM factions" in llm.prompts[1]


def test_unsafe_query_is_fed_back():
    llm = FakeLlm([_reply("DELETE FROM factions"), _reply(GOOD)])
    out = SqlRag(llm)("Which faction are Boyz from?")
    assert out.error is None
    assert "only SELECT / WITH" in llm.prompts[1]


def test_empty_result_triggers_one_recheck():
    empty = "SELECT name FROM factions WHERE name = 'Ork'"
    llm = FakeLlm([_reply(empty), _reply(GOOD)])
    out = SqlRag(llm)("Which faction are Boyz from?")
    assert out.rows == [{"name": "Orks"}]
    assert "returned no rows" in llm.prompts[1]


def test_count_of_zero_triggers_one_recheck():
    zero = "SELECT count(*) AS n FROM factions WHERE name = 'Nobody'"
    llm = FakeLlm([_reply(zero), _reply(GOOD)])
    out = SqlRag(llm)("How many factions are called Nobody?")
    assert out.rows == [{"name": "Orks"}]
    assert "returned 0" in llm.prompts[1]
    assert "another table or column" in llm.prompts[1]


def test_repeating_a_count_of_zero_is_accepted():
    zero = "SELECT count(*) AS n FROM factions WHERE name = 'Nobody'"
    llm = FakeLlm([_reply(zero), _reply(zero)])
    rag = SqlRag(llm)
    assert rag("How many factions are called Nobody?").rows == [{"n": 0}]
    assert len(rag.last_attempts) == 2


def test_nonzero_count_is_not_rechecked():
    llm = FakeLlm([_reply("SELECT count(*) AS n FROM factions")])
    rag = SqlRag(llm)
    assert rag("How many factions?").error is None
    assert len(rag.last_attempts) == 1


def test_prompt_separates_abilities_keywords_and_weapon_abilities():
    prompt = build_prompt("anything", max_rows=50)
    assert "datasheets_abilities.abilityId" in prompt
    assert "lower(description)" in prompt


def test_repeating_an_empty_query_is_accepted():
    empty = "SELECT name FROM factions WHERE name = 'Nobody'"
    llm = FakeLlm([_reply(empty), _reply(empty)])
    rag = SqlRag(llm)
    out = rag("Which faction is called Nobody?")
    assert out.error is None and out.rows == []
    assert len(rag.last_attempts) == 2


def test_gives_up_after_max_attempts():
    llm = FakeLlm([_reply("SELECT bad FROM factions")] * 3)
    rag = SqlRag(llm, max_attempts=3)
    out = rag("?")
    assert out.error and "no such column" in out.error
    assert len(llm.prompts) == 3
    assert llm.prompts[2].count("PREVIOUS ATTEMPT") == 2


def test_max_rows_is_respected():
    llm = FakeLlm([_reply("SELECT name FROM datasheets")])
    out = SqlRag(llm)("List datasheets", max_rows=5)
    assert len(out.rows) == 5
    assert "at most 5" in llm.prompts[0]


def test_total_rows_reports_what_the_cap_hid():
    llm = FakeLlm([_reply("SELECT name FROM datasheets")])
    out = SqlRag(llm)("List datasheets", max_rows=5)
    assert out.total_rows == 1680


def test_llm_failure_comes_back_in_error():
    class FailingLlm:
        def complete_json(self, prompt, schema):
            raise RuntimeError("429 quota")

    out = SqlRag(FailingLlm())("Which faction are Boyz from?")
    assert out.rows == [] and out.sql == ""
    assert "LLM call failed: 429 quota" in out.error


def test_llm_failure_on_retry_keeps_the_last_query():
    class FailsSecondTime:
        calls = 0

        def complete_json(self, prompt, schema):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("429 quota")
            return _reply("SELECT nme FROM factions")

    out = SqlRag(FailsSecondTime())("Which faction are Boyz from?")
    assert out.sql == "SELECT nme FROM factions"
    assert "LLM call failed" in out.error

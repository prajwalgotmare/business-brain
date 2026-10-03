from business_brain.api.routes.auth import _DEMO_PERSONAS


def test_demo_personas_are_non_secret_and_cover_all_roles() -> None:
    assert len(_DEMO_PERSONAS) == 4
    assert {persona.role.value for persona in _DEMO_PERSONAS} == {
        "founder_cfo",
        "logistics_manager",
        "staff_accountant",
        "support_intern",
    }
    assert all(persona.user_id.startswith("demo-") for persona in _DEMO_PERSONAS)

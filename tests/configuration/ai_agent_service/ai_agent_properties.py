from snakeboot.configuration import Section, configuration_properties


@configuration_properties("ai_agent")
class AiAgentProperties(Section):
    """A section whose name a host also gives a variable of its own: AI_AGENT."""

    model: str
    temperature: float

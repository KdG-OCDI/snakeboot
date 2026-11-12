from snakeboot.configuration import Section, configuration_properties


@configuration_properties("loans")
class LoanProperties(Section):
    """The section `[loans]`: how many books a member may have at once."""

    max_loans: int

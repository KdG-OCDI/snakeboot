"""An application whose component scan holds the working jobs."""

from snakeboot.component_scan import application_root


@application_root(base_packages=("tests.scheduling.sample_jobs.working",))
class WorkingJobsApplication:
    """Stands in for an application with scheduled methods."""

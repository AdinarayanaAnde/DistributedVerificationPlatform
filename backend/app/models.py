from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    runs = relationship("Run", back_populates="client")


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    locks = relationship("ResourceLock", back_populates="resource")
    queues = relationship("QueueEntry", back_populates="resource")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    selected_tests: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    setup_config_id: Mapped[int | None] = mapped_column(ForeignKey("setup_configurations.id"), nullable=True)
    setup_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pending, running, passed, failed, skipped
    teardown_config_id: Mapped[int | None] = mapped_column(ForeignKey("teardown_configurations.id"), nullable=True)
    teardown_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pending, running, passed, failed, skipped
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client = relationship("Client", back_populates="runs")
    resource = relationship("Resource")
    setup_config = relationship("SetupConfiguration")
    teardown_config = relationship("TeardownConfiguration")
    logs = relationship("LogEntry", back_populates="run", order_by="LogEntry.timestamp")


class ResourceLock(Base):
    __tablename__ = "resource_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resource = relationship("Resource", back_populates="locks")
    run = relationship("Run")


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="waiting", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("Run")
    client = relationship("Client")
    resource = relationship("Resource", back_populates="queues")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(32), default="INFO")
    source: Mapped[str] = mapped_column(String(64), default="runner")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("Run", back_populates="logs")


class ReportData(Base):
    __tablename__ = "report_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # "html", "json", "allure", "coverage"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("Run")


class CustomSuite(Base):
    __tablename__ = "custom_suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tests: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("Client")


class RunSuiteLink(Base):
    """Track which suites were used for each run."""
    __tablename__ = "run_suite_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    suite_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    run = relationship("Run")


class SetupConfiguration(Base):
    __tablename__ = "setup_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps = relationship("SetupStep", back_populates="config", order_by="SetupStep.order")
    creator = relationship("Client")


class SetupStep(Base):
    __tablename__ = "setup_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("setup_configurations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), default="command")  # command, script, check, env
    command: Mapped[str] = mapped_column(Text, nullable=False)
    timeout: Mapped[int] = mapped_column(Integer, default=300)
    order: Mapped[int] = mapped_column(Integer, default=0)
    on_failure: Mapped[str] = mapped_column(String(32), default="fail")  # fail, skip, continue
    env_vars: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    config = relationship("SetupConfiguration", back_populates="steps")


class TeardownConfiguration(Base):
    __tablename__ = "teardown_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps = relationship("TeardownStep", back_populates="config", order_by="TeardownStep.order")
    creator = relationship("Client")


class TeardownStep(Base):
    __tablename__ = "teardown_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("teardown_configurations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), default="command")  # command, script, check, env
    command: Mapped[str] = mapped_column(Text, nullable=False)
    timeout: Mapped[int] = mapped_column(Integer, default=300)
    order: Mapped[int] = mapped_column(Integer, default=0)
    on_failure: Mapped[str] = mapped_column(String(32), default="continue")  # continue, fail, skip
    env_vars: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    config = relationship("TeardownConfiguration", back_populates="steps")

CREATE TABLE depot_shelf (
    shelf_id UUID NOT NULL,
    label VARCHAR(40) NOT NULL,
    PRIMARY KEY (shelf_id)
);

CREATE TABLE snakeboot_event_publication (
    publication_id UUID NOT NULL,
    listener_id VARCHAR(500) NOT NULL,
    event_type VARCHAR(500) NOT NULL,
    event JSONB NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    due_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attempts INTEGER NOT NULL,
    last_failure TEXT,
    PRIMARY KEY (publication_id)
);

CREATE INDEX snakeboot_event_publication_due_idx ON snakeboot_event_publication (due_at);

CREATE TABLE snakeboot_scheduler_lock (
    name VARCHAR(200) NOT NULL,
    lock_until TIMESTAMP WITH TIME ZONE NOT NULL,
    locked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    locked_by VARCHAR(255) NOT NULL,
    PRIMARY KEY (name)
);

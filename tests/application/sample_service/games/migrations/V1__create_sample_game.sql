CREATE TABLE sample_game (
    game_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,
    board JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (game_id)
);

CREATE INDEX sample_game_status_idx ON sample_game (status);

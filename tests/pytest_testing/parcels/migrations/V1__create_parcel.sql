CREATE TABLE parcel (
    parcel_id UUID NOT NULL,
    recipient VARCHAR(100) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (parcel_id),
    CONSTRAINT parcel_status_check CHECK (status IN ('SENT', 'DELIVERED'))
);

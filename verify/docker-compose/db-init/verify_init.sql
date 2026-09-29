-- Inji Verify 0.18.2 database schema, assembled from inji-verify/db_scripts/inji_verify/ddl (authoritative).
-- The database itself (inji_verify) is created by POSTGRES_DB in docker-compose.yaml.
--
-- Why not upstream's docker-compose/db-init/init.sql: at v0.18.2 it keeps vp_token NOT NULL and lacks the
-- response_code columns the 0.18.2 VPSubmission entity writes (ddl-auto=none), so submissions would fail
-- to insert. See docs/FINDINGS.md, F6.
ALTER DATABASE inji_verify SET search_path TO verify,pg_catalog,public;
CREATE SCHEMA IF NOT EXISTS verify;
SET search_path TO verify,pg_catalog,public;

-- from ddl/verify-authorization_request_details.sql
CREATE TABLE authorization_request_details(
                              request_id character varying(40) NOT NULL,
                              transaction_id character varying(40) NOT NULL,
                              authorization_details text NOT NULL,
                              expires_at bigint NOT NULL
);
COMMENT ON TABLE authorization_request_details IS 'Authorization RequestCreate Response table: Store details of all the verifiable presentation authorization requests created';
COMMENT ON COLUMN authorization_request_details.request_id IS 'Request ID: request ID of newly created authorization request';
COMMENT ON COLUMN authorization_request_details.transaction_id IS 'Transaction ID: transaction ID of newly created authorization request';
COMMENT ON COLUMN authorization_request_details.authorization_details IS 'Authorization Details: this object contains all the details necessary for a openID4VP sharing request';
COMMENT ON COLUMN authorization_request_details.expires_at IS 'Expires At: expiry of the newly created authorization request';

-- from ddl/verify-presentation_definition.sql
CREATE TABLE presentation_definition(
                                                      id character varying(36) NOT NULL,
                                                      input_descriptors text NOT NULL,
                                                      name character varying(500),
                                                      purpose character varying(500),
                                                      vp_format text,
                                                      submission_requirements text
);

COMMENT ON TABLE presentation_definition IS 'Presentation Definition table: Store details of predefined Presentation Definitions used in openID4VP sharing';
COMMENT ON COLUMN presentation_definition.id IS 'ID: The field should provide a unique ID for the desired context';
COMMENT ON COLUMN presentation_definition.input_descriptors IS 'Input Descriptors: Input Descriptors Objects are populated with properties describing what type of input data/Claim';
COMMENT ON COLUMN presentation_definition.name IS 'Name: this should be a human-friendly string intended to constitute a distinctive designation of the Presentation Definition';
COMMENT ON COLUMN presentation_definition.purpose IS 'Purpose: this describes the purpose for which the Presentation Definition inputs are being used for.';
COMMENT ON COLUMN presentation_definition.vp_format IS 'Format: this describes which algorithms the Verifier supports for the format.';
COMMENT ON COLUMN presentation_definition.submission_requirements IS 'Submission Requirements: express what combinations of inputs must be submitted to comply with its requirements for proceeding in a flow';

-- from ddl/verify-vp_submission.sql
CREATE TABLE vp_submission(
                            request_id character varying(40) NOT NULL,
                            vp_token VARCHAR NULL,
                            presentation_submission text NULL,
                            error character varying(100) NULL,
                            error_description character varying(200) NULL,
                            response_code character varying(200) NULL,
                            response_code_expiry_at TIMESTAMP WITH TIME ZONE NULL,
                            response_code_used boolean DEFAULT false,
                            CONSTRAINT uq_vp_submission_response_code UNIQUE (response_code)
);

CREATE INDEX IF NOT EXISTS idx_vp_submission_response_code ON vp_submission (response_code);
COMMENT ON TABLE vp_submission IS 'VP Submission table: Store details of all the verifiable presentation submissions';
COMMENT ON COLUMN vp_submission.request_id IS 'Request ID: request ID verifiable presentation submission';
COMMENT ON COLUMN vp_submission.vp_token IS 'VP Token: base64 encoded VP submission result. This can be null, in case of error.';
COMMENT ON COLUMN vp_submission.presentation_submission IS 'Presentation Submission: presentation submission object which has details on where to find VC / Claims. This can be null, in case of error.';
COMMENT ON COLUMN vp_submission.error IS 'Error: error code as sent by wallet related to VP submission. This can be null, in case there is no error.';
COMMENT ON COLUMN vp_submission.error_description IS 'Error Description: error message as sent by wallet related to VP submission. This can be null, in case there is no error.';
COMMENT ON COLUMN vp_submission.response_code IS 'Response Code: A short-lived, one-time credential used to ensure only the authorized receiver can fetch the Verifiable Presentation response.';
COMMENT ON COLUMN vp_submission.response_code_expiry_at IS 'Response Code Expiry At: The UTC timestamp defining the end of the validity window for the response code.';
COMMENT ON COLUMN vp_submission.response_code_used IS 'Response Code Used: A boolean flag for replay protection. Ensures that the response code is consumed exactly once and cannot be reused.';

-- from ddl/verify-vc_submission.sql
CREATE TABLE vc_submission(
                          transaction_id character varying(40) NOT NULL,
                          vc text NOT NULL
);

COMMENT ON TABLE vc_submission IS 'VC Submission table: Store details of all the verifiable credentials submissions';
COMMENT ON COLUMN vc_submission.transaction_id IS 'Transaction ID: transaction ID verifiable credentials submission';
COMMENT ON COLUMN vc_submission.vc IS 'VC: base64 encoded VC submission result';

# Transcript privacy notice

CurriculumAdvisor analyses a transcript only for the request initiated by the student.

## What the service processes

A transcript may contain a student name, student number, programme details, course codes, marks, and result statuses. The application extracts only the information required to produce the academic rules report.

## Retention

- Uploaded PDF bytes are held in application memory for the duration of the request.
- Extracted transcript content is not written to a database or file by the application.
- The application does not create student accounts or retain academic histories.
- Analysis responses are marked `Cache-Control: no-store`.

## Logs

Application request logs exclude request bodies, query strings, uploaded file contents, extracted transcript text, student names, student numbers, marks, and course-result payloads. Operational logs may contain a random request ID, endpoint path, response status, duration, upload byte count, parsing duration, and number of parsed results.

Hosting-provider access logs and operational settings must be reviewed before launch to ensure they do not capture request bodies. Access to production logs should be limited to authorised maintainers and governed by an explicit retention period.

## Model training

The application does not send transcripts to a generative-AI model. Transcript data is not used by this application for model training.

## Student responsibility

Students should upload only their own academic records or records they are authorised to process. They should close shared-browser sessions after use and should not treat the report as an official Faculty or Senate decision.

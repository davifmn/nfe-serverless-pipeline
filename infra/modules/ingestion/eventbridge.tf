# Domain events for downstream consumers (accounting, analytics) without coupling.

resource "aws_cloudwatch_event_bus" "events" {
  name = "${var.name}-events"
}

# Keeps a replayable copy of every event, e.g. to backfill a new consumer.
resource "aws_cloudwatch_event_archive" "events" {
  name             = "${var.name}-events"
  event_source_arn = aws_cloudwatch_event_bus.events.arn
  retention_days   = var.event_archive_days
}

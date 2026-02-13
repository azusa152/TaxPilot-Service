"""Tests for document ingestion infrastructure."""


def test_ingestor_should_be_instantiable():
    """Verify DocumentIngestor can be created (markitdown is importable).

    Arrange: Import DocumentIngestor class.
    Act: Instantiate the ingestor.
    Assert: Instance is created without error.
    """
    # Arrange & Act
    from src.infrastructure.ingestion import DocumentIngestor

    ingestor = DocumentIngestor()

    # Assert
    assert ingestor is not None

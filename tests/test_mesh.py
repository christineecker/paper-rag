from lib import mesh as mesh_lib

SAMPLE_XML = """<?xml version="1.0"?>
<DescriptorRecordSet LanguageCode="eng">
<DescriptorRecord DescriptorClass="1">
  <DescriptorUI>D001321</DescriptorUI>
  <DescriptorName><String>Autism Spectrum Disorder</String></DescriptorName>
  <ConceptList>
    <Concept PreferredConceptYN="Y">
      <ConceptUI>M0001</ConceptUI>
      <ConceptName><String>Autism Spectrum Disorder</String></ConceptName>
      <TermList>
        <Term ConceptPreferredTermYN="Y">
          <TermUI>T0001</TermUI>
          <String>Autism Spectrum Disorder</String>
        </Term>
        <Term ConceptPreferredTermYN="N">
          <TermUI>T0002</TermUI>
          <String>Autism</String>
        </Term>
      </TermList>
    </Concept>
  </ConceptList>
</DescriptorRecord>
<DescriptorRecord DescriptorClass="1">
  <DescriptorUI>D008279</DescriptorUI>
  <DescriptorName><String>Magnetic Resonance Imaging</String></DescriptorName>
  <ConceptList>
    <Concept PreferredConceptYN="Y">
      <ConceptUI>M0002</ConceptUI>
      <ConceptName><String>Magnetic Resonance Imaging</String></ConceptName>
      <TermList>
        <Term ConceptPreferredTermYN="Y">
          <TermUI>T0003</TermUI>
          <String>Magnetic Resonance Imaging</String>
        </Term>
        <Term ConceptPreferredTermYN="N">
          <TermUI>T0004</TermUI>
          <String>structural MRI</String>
        </Term>
      </TermList>
    </Concept>
  </ConceptList>
</DescriptorRecord>
</DescriptorRecordSet>
"""


def test_build_and_lookup(tmp_path):
    xml_path = tmp_path / "desc-test.xml"
    xml_path.write_text(SAMPLE_XML)

    index_path = mesh_lib.build_mesh_index(xml_path, index_path=tmp_path / "desc-test.sqlite3")
    assert index_path.exists()

    assert mesh_lib.lookup_descriptor("autism", index_path=index_path) == "Autism Spectrum Disorder"
    assert mesh_lib.lookup_descriptor("AUTISM", index_path=index_path) == "Autism Spectrum Disorder"
    assert mesh_lib.lookup_descriptor("structural mri", index_path=index_path) == "Magnetic Resonance Imaging"
    assert mesh_lib.lookup_descriptor("unrelated term", index_path=index_path) is None


def test_lookup_without_index_returns_none(tmp_path):
    missing = tmp_path / "does-not-exist.sqlite3"
    assert mesh_lib.lookup_descriptor("autism", index_path=missing) is None


def test_latest_available_index_picks_newest(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_RAG_MESH_CACHE_DIR", str(tmp_path))
    (tmp_path / "desc2024.sqlite3").write_bytes(b"")
    (tmp_path / "desc2026.sqlite3").write_bytes(b"")
    (tmp_path / "desc2025.sqlite3").write_bytes(b"")
    assert mesh_lib.latest_available_index().name == "desc2026.sqlite3"

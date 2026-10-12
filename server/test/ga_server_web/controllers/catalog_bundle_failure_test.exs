defmodule GAWeb.CatalogBundleFailureTest do
  use GAWeb.ConnCase, async: false

  alias GA.Catalog

  setup do
    directory = Path.join(System.tmp_dir!(), "ga-catalog-#{System.unique_integer([:positive])}")
    File.mkdir_p!(Path.join(directory, "library"))
    File.mkdir_p!(Path.join(directory, "content"))
    previous = Application.get_env(:ga_server, :catalog_priv_dir)
    Application.put_env(:ga_server, :catalog_priv_dir, directory)

    File.write!(
      Path.join(directory, "library/catalog.json"),
      Jason.encode!(%{
        works: [
          %{
            id: "ga-001",
            title: "Fixture work",
            content_completeness: "complete",
            catalog_passage_count: 1,
            passages: [%{id: "a", title: "Fixture passage", source_label: "Fixture source"}],
            content_path: "/api/catalog/ga-001/content"
          },
          %{id: "ga-002", title: "Unavailable work", state: "import_queue"}
        ]
      })
    )

    on_exit(fn ->
      if previous,
        do: Application.put_env(:ga_server, :catalog_priv_dir, previous),
        else: Application.delete_env(:ga_server, :catalog_priv_dir)

      File.rm_rf!(directory)
    end)

    {:ok, directory: directory}
  end

  test "missing bundles remain visible in the catalog but have no downloadable manifest", %{
    conn: conn
  } do
    assert Catalog.get_reader_work("ga-001")
    assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
    manifest = conn |> get(~p"/api/catalog/ga-001/manifest") |> json_response(200)
    assert manifest["bundles"] == []
    refute Map.has_key?(manifest["work"], "content_path")

    assert conn |> get(~p"/api/catalog/ga-002") |> json_response(200)
    assert conn |> get(~p"/api/catalog/ga-002/content") |> response(404) == ""
  end

  test "invalid JSON and malformed or mismatched payloads return 404 without advertising downloads",
       %{
         conn: conn,
         directory: directory
       } do
    malformed = [
      "{broken",
      Jason.encode!(%{work_id: "ga-001", passages: nil}),
      Jason.encode!(%{work_id: "ga-001", passages: [nil]}),
      Jason.encode!(%{work_id: "ga-001", passages: [passage(%{text: ""})]}),
      Jason.encode!(%{work_id: "ga-001", passages: [passage(%{title: nil})]}),
      Jason.encode!(%{work_id: "ga-001", passages: [passage(%{metadata: nil})]}),
      Jason.encode!(%{
        work_id: "ga-001",
        passages: [passage(%{metadata: %{page_numbers: "15"}})]
      }),
      Jason.encode!(%{
        work_id: "ga-001",
        passages: [passage(%{metadata: %{annotations: [nil]}})]
      }),
      Jason.encode!(%{work_id: "ga-001", passages: [passage()], metadata: []}),
      Jason.encode!(%{work_id: "ga-001", passages: [passage()], passage_count: 2}),
      Jason.encode!(%{work_id: "ga-002", passages: [passage()]}),
      Jason.encode!(%{
        work_id: "ga-001",
        passages: [passage(), passage()]
      })
    ]

    for body <- malformed do
      body =
        case Jason.decode(body) do
          {:ok, payload} -> Jason.encode!(Map.put(payload, "content_completeness", "complete"))
          _ -> body
        end

      File.write!(Path.join(directory, "content/ga-001.json"), body)
      assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
      assert Catalog.manifest("ga-001").bundles == []
      assert Catalog.proofing_content("ga-001") == nil
    end
  end

  test "source text is removed recursively and checksum follows replacement bundle bytes", %{
    directory: directory
  } do
    payload = %{
      work_id: "ga-001",
      content_completeness: "complete",
      source_text: "Private source copy",
      passages: [
        passage(%{
          text: "Reader text [15]",
          source_text: "Source text",
          metadata: %{source_text: "Source text"}
        })
      ]
    }

    path = Path.join(directory, "content/ga-001.json")
    File.write!(path, Jason.encode!(payload))
    first = Catalog.download("ga-001")
    assert first.payload["passages"] |> hd() |> get_in(["metadata", "page_numbers"]) == [15]
    refute String.contains?(first.body, "source_text")
    assert Catalog.proofing_content("ga-001")["source_text"] == "Private source copy"

    File.write!(
      path,
      Jason.encode!(put_in(payload, [:passages, Access.at(0), :text], "Revised reader text"))
    )

    second = Catalog.download("ga-001")
    refute first.checksum == second.checksum
    assert hd(Catalog.manifest("ga-001").bundles).checksum == second.checksum

    File.rm!(path)
    assert Catalog.download("ga-001") == nil
    assert Catalog.manifest("ga-001").bundles == []
  end

  test "unknown and traversal IDs never read arbitrary files" do
    for id <- ["ga-999", "../ga-001", "ga-001/../ga-002", "ga-001\n", nil] do
      assert Catalog.content(id) == nil
      assert Catalog.proofing_content(id) == nil
      assert Catalog.download(id) == nil
    end
  end

  test "compressed release bundles replace older JSON and damaged gzip returns 404", %{
    conn: conn,
    directory: directory
  } do
    json = Path.join(directory, "content/ga-001.json")
    gzip = json <> ".gz"

    File.write!(
      json,
      Jason.encode!(%{
        work_id: "ga-001",
        content_completeness: "partial",
        passages: [passage(%{id: "old", text: "Old seed"})]
      })
    )

    File.write!(
      gzip,
      :zlib.gzip(
        Jason.encode!(%{
          work_id: "ga-001",
          content_completeness: "complete",
          passages: [passage(%{text: "Complete import"})]
        })
      )
    )

    assert [%{"id" => "a", "text" => "Complete import"}] = Catalog.content("ga-001")["passages"]
    assert conn |> get(~p"/api/catalog/ga-001/content") |> json_response(200)

    File.write!(gzip, "not gzip")
    assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
    assert Catalog.manifest("ga-001").bundles == []
  end

  test "partial or excerpt payloads and imports without completeness are never served", %{
    directory: directory,
    conn: conn
  } do
    for flags <- [
          %{},
          %{content_completeness: "partial"},
          %{content_completeness: "excerpt"},
          %{content_completeness: "unavailable"},
          %{content_completeness: "complete", completeness: "partial"},
          %{content_completeness: "complete", state: "published_seed"}
        ] do
      payload = Map.merge(%{work_id: "ga-001", passages: [passage()]}, flags)
      File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(payload))
      assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
      assert Catalog.manifest("ga-001").bundles == []
    end
  end

  test "GA 120 fallback ignores legacy excerpts and requires the complete eleven-lecture gzip", %{
    directory: directory
  } do
    File.rm!(Path.join(directory, "library/catalog.json"))
    json = Path.join(directory, "content/ga-120.json")
    gzip = json <> ".gz"
    File.write!(json, Jason.encode!(%{work_id: "ga-120", passages: [passage()]}))
    work = Catalog.get_reader_work("ga-120")
    assert work.state == "import_queue"
    assert work.content_completeness == "unavailable"
    assert work.passages == []
    refute Map.has_key?(work, :content_path)
    assert Catalog.content("ga-120") == nil

    payload = %{work_id: "ga-120", content_completeness: "complete", passages: [passage()]}
    File.write!(gzip, :zlib.gzip(Jason.encode!(payload)))
    assert Catalog.content("ga-120") == nil

    passages = Enum.map(1..11, &passage(%{id: "lecture-#{&1}", title: "Lecture #{&1}"}))
    File.write!(gzip, :zlib.gzip(Jason.encode!(%{payload | passages: passages})))
    assert Catalog.get_reader_work("ga-120").content_completeness == "complete"
    assert length(Catalog.content("ga-120")["passages"]) == 11
  end

  test "catalog partial and seed flags prevent complete payloads from becoming downloadable", %{
    directory: directory
  } do
    File.write!(
      Path.join(directory, "content/ga-001.json"),
      Jason.encode!(%{work_id: "ga-001", content_completeness: "complete", passages: [passage()]})
    )

    for flags <- [
          %{content_completeness: "partial"},
          %{content_completeness: "excerpt"},
          %{content_completeness: "complete", completeness: "partial"},
          %{content_completeness: "complete", state: "published_seed"}
        ] do
      work =
        Map.merge(
          %{id: "ga-001", title: "Fixture work", content_path: "/api/catalog/ga-001/content"},
          flags
        )

      path = Path.join(directory, "library/catalog.json")
      File.write!(path, Jason.encode!(%{works: [work]}))
      :persistent_term.erase({Catalog, :metadata, path})
      refute Map.has_key?(Catalog.get_reader_work("ga-001"), :content_path)
      assert Catalog.content("ga-001") == nil
      assert Catalog.manifest("ga-001").bundles == []
    end
  end

  test "self-consistent truncated or substituted bundles cannot override full catalog passage metadata",
       %{directory: directory, conn: conn} do
    work = %{
      id: "ga-001",
      title: "Fixture work",
      content_completeness: "complete",
      content_path: "/api/catalog/ga-001/content",
      catalog_passage_count: 2,
      passages: [%{id: "a"}, %{id: "b"}]
    }

    path = Path.join(directory, "library/catalog.json")
    File.write!(path, Jason.encode!(%{works: [work]}))
    :persistent_term.erase({Catalog, :metadata, path})

    for passages <- [[passage()], [passage(), passage(%{id: "c"})]] do
      payload = %{
        work_id: "ga-001",
        content_completeness: "complete",
        passage_count: length(passages),
        passages: passages
      }

      File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(payload))
      assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
      assert Catalog.manifest("ga-001").bundles == []
    end

    payload = %{
      work_id: "ga-001",
      content_completeness: "complete",
      passages: [passage(), passage(%{id: "b"})]
    }

    File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(payload))
    assert Catalog.content("ga-001")["passage_count"] == 2
  end

  test "validated structure, anchored notes, pages and TOC retain exact canonical text", %{
    directory: directory,
    conn: conn
  } do
    payload = structured_payload()
    path = Path.join(directory, "content/ga-001.json")
    File.write!(path, Jason.encode!(payload))
    served = conn |> get(~p"/api/catalog/ga-001/content") |> json_response(200)
    actual = hd(served["passages"])
    expected = hd(payload.passages)

    assert actual["text"] == expected.text

    assert actual["checksum"] ==
             :crypto.hash(:sha256, expected.text) |> Base.encode16(case: :lower)

    assert actual["metadata"] == Jason.decode!(Jason.encode!(expected.metadata))
    assert served["table_of_contents"] == Jason.decode!(Jason.encode!(payload.table_of_contents))
    assert served["metadata"]["page_number_source"] == "original_doc_footer"
    assert Catalog.manifest("ga-001").bundles != []

    # TOC offsets alone also identify already-canonical text.
    payload = put_in(payload, [:passages, Access.at(0), :metadata], %{})
    File.write!(path, Jason.encode!(payload))
    assert hd(Catalog.content("ga-001")["passages"])["text"] == expected.text
  end

  test "invalid offset structures cannot be downloaded or advertised", %{
    directory: directory,
    conn: conn
  } do
    payload = structured_payload()
    block = [:passages, Access.at(0), :metadata, :reading_blocks, Access.at(0)]
    note = [:passages, Access.at(0), :metadata, :annotations, Access.at(0)]
    anchor = [:passages, Access.at(0), :metadata, :page_anchors, Access.at(0)]
    toc = [:table_of_contents, Access.at(0)]

    malformed = [
      put_in(payload, block ++ [:end_offset], 1),
      put_in(payload, block ++ [:start_offset], -1),
      put_in(payload, block ++ [:end_offset], 100_000),
      put_in(payload, block ++ [:kind], "unknown"),
      put_in(payload, block ++ [:level], 0),
      put_in(payload, block ++ [:level], 2.5),
      put_in(payload, block ++ [:poem_start], "true"),
      update_in(payload, [:passages, Access.at(0), :metadata, :reading_blocks], &Enum.reverse/1),
      update_in(payload, [:passages, Access.at(0), :metadata, :reading_blocks], &tl/1),
      update_in(
        payload,
        [:passages, Access.at(0), :metadata, :reading_blocks],
        &Enum.drop(&1, -1)
      ),
      put_in(
        payload,
        [:passages, Access.at(0), :metadata, :reading_blocks, Access.at(1), :start_offset],
        2
      ),
      put_in(payload, [:passages, Access.at(0), :metadata, :reading_blocks], %{}),
      put_in(payload, [:passages, Access.at(0), :metadata, :group_title], 12),
      put_in(payload, anchor ++ [:start_offset], 1),
      put_in(payload, anchor ++ [:page], -1),
      put_in(payload, anchor ++ [:source], nil),
      put_in(payload, anchor ++ [:confidence], []),
      put_in(payload, anchor ++ [:source_section], -1),
      update_in(payload, [:passages, Access.at(0), :metadata, :page_anchors], &Enum.reverse/1),
      put_in(payload, note ++ [:start_offset], nil),
      put_in(payload, note ++ [:end_offset], nil),
      put_in(payload, note ++ [:end_offset], 100_000),
      put_in(payload, note ++ [:marker], "* wrong"),
      update_in(payload, note, &Map.delete(&1, :end_offset)),
      put_in(payload, toc ++ [:start_offset], 1),
      put_in(payload, toc ++ [:passage_id], "missing"),
      put_in(payload, toc ++ [:parent_id], "calendar"),
      put_in(payload, toc ++ [:parent_id], "missing"),
      update_in(payload, [:table_of_contents], &(&1 ++ [hd(&1)])),
      put_in(payload, [:table_of_contents], %{})
    ]

    for candidate <- malformed do
      File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(candidate))
      assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
      assert Catalog.download("ga-001") == nil
      assert Catalog.manifest("ga-001").bundles == []
    end
  end

  defp structured_payload do
    text = "📖 Frühling\n\n1\n\nEin  Vers [15] *\nNoch ein Vers *"
    heading_end = utf16_length("📖 Frühling")
    number_start = heading_end + 2
    verse_start = number_start + 3
    marker_start = text |> String.split("*", parts: 2) |> hd() |> utf16_length()

    %{
      work_id: "ga-001",
      content_completeness: "complete",
      passages: [
        passage(%{
          text: text,
          metadata: %{
            group_title: "Anthroposophischer Seelenkalender",
            reading_blocks: [
              %{kind: "heading", start_offset: 0, end_offset: heading_end, level: 1},
              %{
                kind: "heading",
                start_offset: number_start,
                end_offset: number_start + 1,
                level: 2
              },
              %{
                kind: "verse",
                start_offset: verse_start,
                end_offset: utf16_length(text),
                poem_start: true
              }
            ],
            page_anchors: [
              %{page: 23, start_offset: 0, source: "original_doc_footer"},
              %{page: 24, start_offset: verse_start, source: "original_doc_footer"}
            ],
            annotations: [
              %{
                id: "EPUB/chapter.xhtml#note-1",
                marker: "*",
                text: "Eine Anmerkung",
                start_offset: marker_start,
                end_offset: marker_start + 1
              }
            ]
          }
        })
      ],
      table_of_contents: [
        %{
          id: "calendar",
          title: "Seelenkalender",
          level: 1,
          passage_id: "a",
          start_offset: 0,
          parent_id: nil
        },
        %{
          id: "chapter",
          title: "Frühling",
          level: 2,
          passage_id: "a",
          start_offset: 0,
          parent_id: "calendar"
        },
        %{
          id: "poem",
          title: "1",
          level: 3,
          passage_id: "a",
          start_offset: number_start,
          parent_id: "chapter"
        }
      ]
    }
  end

  defp utf16_length(text) do
    text |> :unicode.characters_to_binary(:utf8, {:utf16, :little}) |> byte_size() |> div(2)
  end

  defp passage(overrides \\ %{}) do
    Map.merge(
      %{id: "a", title: "Fixture passage", source_label: "Fixture source", text: "Reader text"},
      overrides
    )
  end
end

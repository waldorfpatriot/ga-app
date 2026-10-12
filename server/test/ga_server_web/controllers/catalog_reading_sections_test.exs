defmodule GAWeb.CatalogReadingSectionsTest do
  use GAWeb.ConnCase, async: false

  alias GA.Catalog

  setup do
    directory = Path.join(System.tmp_dir!(), "ga-sections-#{System.unique_integer([:positive])}")
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
            title: "Fixture",
            content_completeness: "complete",
            catalog_passage_count: 1,
            content_path: "/api/catalog/ga-001/content",
            passages: [%{id: "a", title: "Vier Sprüche", source_label: "Source"}]
          }
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

  test "source sections retain exact text and sibling anchors", %{
    directory: directory,
    conn: conn
  } do
    payload = payload()
    File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(payload))
    served = conn |> get(~p"/api/catalog/ga-001/content") |> json_response(200)
    passage = hd(served["passages"])
    assert passage["text"] == hd(payload.passages).text

    assert passage["metadata"]["reading_sections"] ==
             Jason.decode!(Jason.encode!(hd(payload.passages).metadata.reading_sections))

    assert Enum.map(served["table_of_contents"], & &1["level"]) == [1, 2, 4, 2, 2]
    assert Catalog.download("ga-001")
  end

  test "sections reject incomplete coverage, invalid boundaries and invented labels", %{
    directory: directory,
    conn: conn
  } do
    payload = payload()
    sections = [:passages, Access.at(0), :metadata, :reading_sections]
    first = sections ++ [Access.at(0)]
    second = sections ++ [Access.at(1)]
    third = sections ++ [Access.at(2)]
    blocks = hd(payload.passages).metadata.reading_blocks
    originals = hd(payload.passages).metadata.reading_sections

    later_heading =
      put_in(payload, sections, [
        %{hd(originals) | title: "TISCHGEBET", end_offset: Enum.at(blocks, 3).end_offset},
        %{List.last(originals) | id: "a-section-2"}
      ])

    later_incipit =
      put_in(payload, first, %{hd(originals) | label_kind: "incipit", title: "Erster Vers"})

    invalid = [
      later_heading,
      later_incipit,
      put_in(payload, sections, []),
      put_in(payload, sections, %{}),
      put_in(payload, first ++ [:start_offset], 1),
      put_in(payload, first ++ [:start_offset], 2),
      put_in(payload, second ++ [:start_offset], hd(blocks).start_offset),
      put_in(payload, second ++ [:end_offset], 9999),
      put_in(payload, first ++ [:end_offset], hd(blocks).end_offset),
      put_in(payload, third ++ [:end_offset], List.last(blocks).end_offset - 1),
      put_in(payload, second ++ [:id], "a"),
      put_in(payload, second ++ [:id], "invented-id"),
      put_in(payload, second ++ [:title], "Invented title"),
      put_in(payload, second ++ [:label_kind], "editorial"),
      put_in(payload, third ++ [:title], "Letzter Spruch Zweite Zeile"),
      put_in(payload, third ++ [:label_kind], "source_title"),
      put_in(payload, first ++ [:label_kind], "incipit"),
      update_in(payload, sections, &Enum.reverse/1),
      update_in(payload, sections, &tl/1),
      update_in(payload, sections, &Enum.drop(&1, -1)),
      put_in(payload, [:passages, Access.at(0), :metadata, :reading_blocks], [])
    ]

    for candidate <- invalid do
      File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(candidate))
      assert conn |> get(~p"/api/catalog/ga-001/content") |> response(404) == ""
      assert Catalog.download("ga-001") == nil
      assert Catalog.manifest("ga-001").bundles == []
    end
  end

  test "section identifiers cannot collide with another passage", %{directory: directory} do
    payload = payload()

    extra = %{
      id: "a-section-2",
      title: "Another passage",
      source_label: "Source",
      text: "Own text",
      metadata: %{}
    }

    payload = %{payload | passages: payload.passages ++ [extra]}

    File.write!(
      Path.join(directory, "library/catalog.json"),
      Jason.encode!(%{
        works: [
          %{
            id: "ga-001",
            title: "Fixture",
            content_completeness: "complete",
            catalog_passage_count: 2,
            content_path: "/api/catalog/ga-001/content",
            passages: Enum.map(payload.passages, &Map.take(&1, [:id, :title, :source_label]))
          }
        ]
      })
    )

    File.write!(Path.join(directory, "content/ga-001.json"), Jason.encode!(payload))
    assert Catalog.download("ga-001") == nil
  end

  defp payload do
    chunks = [
      {"heading", "📖 J"},
      {"verse", "Erster Vers\nZweite Zeile"},
      {"heading", "TISCHGEBET"},
      {"verse", "Gebet\nEnde"},
      {"verse", "Letzter Spruch\nZweite Zeile"}
    ]

    text = chunks |> Enum.map(&elem(&1, 1)) |> Enum.join("\n\n")

    {blocks, _} =
      Enum.map_reduce(chunks, 0, fn {kind, value}, start ->
        finish = start + utf16_length(value)
        block = %{kind: kind, start_offset: start, end_offset: finish}
        block = if kind == "heading", do: Map.put(block, :level, 2), else: block
        {block, finish + 2}
      end)

    sections = [
      %{
        id: "a",
        title: "Vier Sprüche",
        label_kind: "source_title",
        start_offset: 0,
        end_offset: Enum.at(blocks, 1).end_offset
      },
      %{
        id: "a-section-2",
        title: "TISCHGEBET",
        label_kind: "source_title",
        start_offset: Enum.at(blocks, 2).start_offset,
        end_offset: Enum.at(blocks, 3).end_offset
      },
      %{
        id: "a-section-3",
        title: "Letzter Spruch",
        label_kind: "incipit",
        start_offset: Enum.at(blocks, 4).start_offset,
        end_offset: Enum.at(blocks, 4).end_offset
      }
    ]

    group = %{
      id: "group",
      title: "Group",
      level: 1,
      passage_id: "a",
      start_offset: 0,
      parent_id: nil
    }

    siblings =
      Enum.map(sections, fn s ->
        %{
          id: s.id,
          title: s.title,
          level: 2,
          passage_id: "a",
          start_offset: s.start_offset,
          parent_id: "group"
        }
      end)

    inner = %{
      id: "a-heading-1",
      title: "📖 J",
      level: 4,
      passage_id: "a",
      start_offset: 0,
      parent_id: "a"
    }

    %{
      work_id: "ga-001",
      content_completeness: "complete",
      passages: [
        %{
          id: "a",
          title: "Vier Sprüche",
          source_label: "Source",
          text: text,
          metadata: %{reading_blocks: blocks, reading_sections: sections}
        }
      ],
      table_of_contents: [group, hd(siblings), inner | tl(siblings)]
    }
  end

  defp utf16_length(text) do
    text |> :unicode.characters_to_binary(:utf8, {:utf16, :little}) |> byte_size() |> div(2)
  end
end

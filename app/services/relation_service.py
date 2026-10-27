from functools import cmp_to_key
from typing import Any


class RelationService:
    """Declarative relation / lookup resolution shared by all maint tables."""

    def __init__(self, maint_service: Any) -> None:
        self.maint = maint_service
        self.ui = maint_service.ui
        self.store = maint_service.store

    def _require_relation(self, column: dict[str, Any]) -> dict[str, Any]:
        if column.get("field_type") != "relation":
            raise ValueError(f"Field is not relation: {column.get('field')}")
        if "relation" not in column:
            raise KeyError(f"Missing relation config for field: {column['field']}")
        relation = column["relation"]
        for key in ("source_kind", "value_field", "label"):
            if key not in relation:
                raise KeyError(
                    f"Missing relation.{key} for field: {column['field']}"
                )
        return relation

    def _label_text(
        self, relation: dict[str, Any], row: dict[str, Any], language: str
    ) -> str:
        label = relation["label"]
        if "kind" not in label:
            raise KeyError("Missing relation.label.kind")
        if label["kind"] == "label_key":
            if "label_key" not in row or not str(row["label_key"]).strip():
                raise ValueError("Missing label_key for relation label")
            text = self.ui.t(row["label_key"], language)
            if not str(text).strip():
                raise ValueError(f"Empty translated label for key: {row['label_key']}")
            return text
        if label["kind"] == "row_lang_fields":
            if "fields" not in label:
                raise KeyError("Missing relation.label.fields")
            fields = label["fields"]
            if language not in fields:
                raise KeyError(f"Missing relation.label.fields for language: {language}")
            field_name = fields[language]
            if field_name not in row:
                raise KeyError(f"Missing label field on row: {field_name}")
            text = row[field_name]
            if text is None or not str(text).strip():
                raise ValueError(
                    f"Empty relation label field: {field_name} language={language}"
                )
            return str(text)
        raise ValueError(f"Unknown relation.label.kind: {label['kind']}")

    def _related_in_allowed(
        self, rule: dict[str, Any], source_table_key: str
    ) -> set[str]:
        for key in (
            "related_table_key",
            "related_value_field",
            "related_match_field",
            "value",
        ):
            if key not in rule:
                raise KeyError(f"Missing relation filter key for related_in: {key}")
        match_values = rule["value"]
        if not isinstance(match_values, list) or not match_values:
            raise ValueError("related_in value must be a non-empty list")
        related_rows = self._table_rows(rule["related_table_key"])
        group_field = rule.get("related_group_field")
        group_value = rule.get("related_group_value")
        if rule.get("related_group_value_from") == "source_table_key":
            group_value = source_table_key
        allowed: set[str] = set()
        for code in match_values:
            hits = []
            for row in related_rows:
                if group_field is not None:
                    if group_value is None:
                        raise KeyError(
                            "related_in requires related_group_value "
                            "or related_group_value_from"
                        )
                    if row.get(group_field) != group_value:
                        continue
                if row.get(rule["related_match_field"]) != code:
                    continue
                hits.append(row)
            if len(hits) == 0:
                raise ValueError(
                    f"Relation related_in category not found: {code}"
                )
            if len(hits) > 1:
                raise ValueError(
                    f"Relation related_in category duplicated: {code}"
                )
            if hits[0].get("isDisable"):
                raise ValueError(
                    f"Relation related_in category disabled: {code}"
                )
            if rule["related_value_field"] not in hits[0]:
                raise KeyError(
                    f"Missing related_value_field on row: "
                    f"{rule['related_value_field']}"
                )
            allowed.add(str(hits[0][rule["related_value_field"]]))
        return allowed

    def _match_filter(
        self,
        row: dict[str, Any],
        rule: dict[str, Any],
        context: dict[str, Any],
        *,
        for_selection: bool,
    ) -> bool:
        if rule.get("selection_only") and not for_selection:
            return True
        if "field" not in rule or "op" not in rule:
            raise KeyError("Relation filter requires field and op")
        field = rule["field"]
        if field not in row:
            raise KeyError(f"Relation filter field missing on row: {field}")
        actual = row[field]
        op = rule["op"]
        if op == "related_in":
            cache_key = "_related_in_allowed"
            if cache_key not in context:
                source_table_key = context.get("source_table_key")
                if not source_table_key:
                    raise KeyError(
                        "Missing source_table_key for related_in filter"
                    )
                context[cache_key] = self._related_in_allowed(
                    rule, source_table_key
                )
            return str(actual) in context[cache_key]
        if "value_from" in rule:
            source = rule["value_from"]
            if source not in context:
                raise KeyError(f"Missing relation filter context: {source}")
            expected = context[source]
        elif "value" in rule:
            expected = rule["value"]
        else:
            raise KeyError("Relation filter requires value or value_from")
        if op == "eq":
            return actual == expected
        raise ValueError(f"Unsupported relation filter op: {op}")

    def _registry_rows(self) -> list[dict[str, Any]]:
        tables = self.maint.get_tables_config()["tables"]
        rows: list[dict[str, Any]] = []
        for table_key, table_def in tables.items():
            if "supports_categories" not in table_def:
                raise KeyError(
                    f"Missing supports_categories for table_key: {table_key}"
                )
            flag = table_def["supports_categories"]
            if not isinstance(flag, bool):
                raise ValueError(
                    f"supports_categories must be boolean for table_key: {table_key}"
                )
            rows.append(
                {
                    "table_key": table_key,
                    "label_key": table_def["label_key"],
                    "supports_categories": flag,
                }
            )
        return rows

    def _table_rows(self, source_table_key: str) -> list[dict[str, Any]]:
        table_def = self.maint.get_table_def(source_table_key)
        db_table = table_def["db_table"]
        fields = [column["field"] for column in table_def["columns"]]
        sql = f"SELECT {', '.join(fields)} FROM {db_table}"
        rows = self.store.fetchall(sql)
        result = []
        for row in rows:
            item = {field: row[field] for field in fields}
            item["isDisable"] = bool(item.get("isDisable", 0))
            result.append(item)
        return result

    def _load_source_rows(self, relation: dict[str, Any]) -> list[dict[str, Any]]:
        kind = relation["source_kind"]
        if kind == "table_registry":
            return self._registry_rows()
        if kind == "table":
            if "source_table_key" not in relation:
                raise KeyError("Missing relation.source_table_key")
            return self._table_rows(relation["source_table_key"])
        raise ValueError(f"Unknown relation.source_kind: {kind}")

    def _order_by_value(
        self,
        relation: dict[str, Any],
        rule: dict[str, Any],
        row: dict[str, Any],
        language: str,
    ) -> Any:
        if "field_from" in rule:
            if "field" in rule:
                raise KeyError(
                    "relation.order_by cannot set both field and field_from"
                )
            if rule["field_from"] != "label_lang":
                raise ValueError(
                    f"Unknown relation.order_by field_from: {rule['field_from']}"
                )
            label = relation["label"]
            if label.get("kind") != "row_lang_fields":
                raise ValueError(
                    "order_by field_from label_lang requires "
                    "relation.label.kind row_lang_fields"
                )
            if "fields" not in label:
                raise KeyError("Missing relation.label.fields")
            fields = label["fields"]
            if language not in fields:
                raise KeyError(
                    f"Missing relation.label.fields for language: {language}"
                )
            field_name = fields[language]
            if field_name not in row:
                raise KeyError(f"Missing order_by label field on row: {field_name}")
            value = row[field_name]
            if value is None or not str(value).strip():
                raise ValueError(
                    f"Empty relation label field for order_by: {field_name} "
                    f"language={language}"
                )
            return value
        if "field" not in rule:
            raise KeyError("relation.order_by requires field or field_from")
        field = rule["field"]
        if field not in row:
            raise KeyError(f"Missing order_by field on row: {field}")
        return row[field]

    def _sorted_rows(
        self,
        relation: dict[str, Any],
        rows: list[dict[str, Any]],
        language: str,
    ) -> list[dict[str, Any]]:
        order_by = relation.get("order_by") or []
        if not order_by:
            return rows
        for rule in order_by:
            if "dir" not in rule:
                raise KeyError("relation.order_by requires dir")
            if rule["dir"] not in ("asc", "desc"):
                raise ValueError(f"Invalid order_by dir: {rule['dir']}")
            if "field_from" in rule:
                if "field" in rule:
                    raise KeyError(
                        "relation.order_by cannot set both field and field_from"
                    )
                if rule["field_from"] != "label_lang":
                    raise ValueError(
                        f"Unknown relation.order_by field_from: {rule['field_from']}"
                    )
            elif "field" not in rule:
                raise KeyError("relation.order_by requires field or field_from")

        def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
            for rule in order_by:
                left_value = self._order_by_value(relation, rule, left, language)
                right_value = self._order_by_value(relation, rule, right, language)
                if left_value == right_value:
                    continue
                if left_value < right_value:
                    return -1 if rule["dir"] == "asc" else 1
                return 1 if rule["dir"] == "asc" else -1
            return 0

        return sorted(rows, key=cmp_to_key(compare))

    def resolve_options(
        self,
        owner_table_key: str,
        column: dict[str, Any],
        language: str,
        *,
        for_selection: bool,
        include_value: Any | None = None,
    ) -> list[dict[str, Any]]:
        relation = self._require_relation(column)
        source_table_key = None
        if relation["source_kind"] == "table":
            source_table_key = relation["source_table_key"]
        context: dict[str, Any] = {
            "current_table_key": owner_table_key,
            "source_table_key": source_table_key,
        }
        rows = self._load_source_rows(relation)
        filters = relation.get("filters") or []
        matched = []
        for row in rows:
            ok = True
            for rule in filters:
                if not self._match_filter(
                    row, rule, context, for_selection=for_selection
                ):
                    ok = False
                    break
            if ok:
                matched.append(row)

        value_field = relation["value_field"]
        if include_value is not None and str(include_value).strip() != "":
            already = any(
                str(row.get(value_field)) == str(include_value) for row in matched
            )
            if not already:
                for row in rows:
                    if str(row.get(value_field)) == str(include_value):
                        matched.append(row)
                        break
                else:
                    raise ValueError(
                        f"Relation value not found for field {column['field']}: "
                        f"{include_value}"
                    )

        matched = self._sorted_rows(relation, matched, language)
        options = []
        for row in matched:
            if value_field not in row:
                raise KeyError(f"Missing value_field on relation row: {value_field}")
            option: dict[str, Any] = {
                "value": row[value_field],
                "label": self._label_text(relation, row, language),
            }
            for annotate in relation.get("option_annotate") or []:
                for key in (
                    "from_field",
                    "lookup_table_key",
                    "lookup_value_field",
                    "as",
                ):
                    if key not in annotate:
                        raise KeyError(
                            f"Missing relation.option_annotate key: {key}"
                        )
                take_field_lang = bool(annotate.get("take_field_lang"))
                if take_field_lang and "take_field" in annotate:
                    raise KeyError(
                        "option_annotate cannot set both take_field and "
                        "take_field_lang"
                    )
                if (not take_field_lang) and "take_field" not in annotate:
                    raise KeyError(
                        "Missing relation.option_annotate key: take_field"
                    )
                from_field = annotate["from_field"]
                if from_field not in row:
                    raise KeyError(
                        f"Missing option_annotate from_field on row: {from_field}"
                    )
                lookup_rows = self._table_rows(annotate["lookup_table_key"])
                hits = [
                    item
                    for item in lookup_rows
                    if str(item.get(annotate["lookup_value_field"]))
                    == str(row[from_field])
                ]
                if len(hits) != 1:
                    raise ValueError(
                        "option_annotate lookup failed for field "
                        f"{from_field}: hits={len(hits)}"
                    )
                take_field = language if take_field_lang else annotate["take_field"]
                if take_field not in hits[0]:
                    raise KeyError(
                        f"Missing option_annotate take_field: {take_field}"
                    )
                option[annotate["as"]] = hits[0][take_field]
            options.append(option)
        return options

    def resolve_label(
        self,
        owner_table_key: str,
        column: dict[str, Any],
        value: Any,
        language: str,
    ) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError(f"Empty relation value for field: {column['field']}")
        options = self.resolve_options(
            owner_table_key,
            column,
            language,
            for_selection=False,
            include_value=value,
        )
        for option in options:
            if str(option["value"]) == str(value):
                return option["label"]
        raise ValueError(
            f"Unable to resolve relation label for field {column['field']}: {value}"
        )

    def validate_value(
        self,
        owner_table_key: str,
        column: dict[str, Any],
        value: Any,
        language: str,
        *,
        previous_value: Any | None,
    ) -> Any:
        if value is None or str(value).strip() == "":
            raise ValueError(f"Empty relation value for field: {column['field']}")
        if previous_value is not None and str(previous_value) == str(value):
            self.resolve_label(owner_table_key, column, value, language)
            return value
        options = self.resolve_options(
            owner_table_key, column, language, for_selection=True
        )
        allowed = {str(option["value"]) for option in options}
        if str(value) not in allowed:
            raise ValueError(f"Invalid relation value for field: {column['field']}")
        for option in options:
            if str(option["value"]) == str(value):
                return option["value"]
        raise ValueError(f"Invalid relation value for field: {column['field']}")

    def find_inbound_relations(
        self, source_table_key: str
    ) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        tables = self.maint.get_tables_config()["tables"]
        for table_key, table_def in tables.items():
            for column in table_def["columns"]:
                if column.get("field_type") != "relation":
                    continue
                relation = column.get("relation")
                if relation is None:
                    continue
                if relation.get("source_kind") != "table":
                    continue
                if relation.get("source_table_key") != source_table_key:
                    continue
                refs.append(
                    {
                        "table_key": table_key,
                        "field": column["field"],
                        "value_field": relation["value_field"],
                        "db_table": table_def["db_table"],
                    }
                )
        return refs

    def is_value_referenced(self, source_table_key: str, value: Any) -> bool:
        if value is None or str(value).strip() == "":
            return False
        for ref in self.find_inbound_relations(source_table_key):
            sql = (
                f"SELECT 1 AS hit FROM {ref['db_table']} "
                f"WHERE CAST({ref['field']} AS TEXT) = ? LIMIT 1"
            )
            row = self.store.fetchone(sql, (str(value),))
            if row is not None:
                return True
        return False

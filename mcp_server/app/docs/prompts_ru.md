# Подсказки MCP Bitrix24 (ru-RU)

Этот файл содержит локализованные подсказки, описание инструментов и готовые примеры запросов.  
Все структуры данных ниже извлекаются сервером во время запуска, поэтому правки можно вносить без изменения кода.

<!-- prompts:data
{
  "locale": "ru",
  "initialize": {
    "summary": "Работайте с данными Bitrix24 через инструменты списка и ресурсы. Все ответы возвращаются в structuredContent.result полностью, а content содержит краткие выводы.",
    "structured": [
      {
        "title": "Свежие лиды",
        "description": "Отсортируйте по дате изменения и ограничьте выборку диапазоном по дате создания.",
        "order": {"DATE_MODIFY": "DESC"},
        "filter": {
          ">=DATE_CREATE": "2024-06-01T00:00:00Z",
          "<=DATE_CREATE": "2024-06-02T00:00:00Z"
        },
        "limit": 50
      },
      {
        "title": "Лиды назначенные мне",
        "description": "Используйте фильтр `=ASSIGNED_BY_ID` с идентификатором ответственного и при необходимости ограничьте статусом.",
        "order": {"DATE_CREATE": "DESC"},
        "filter": {
          "=ASSIGNED_BY_ID": "123",
          "=STATUS_ID": "NEW"
        },
        "limit": 20
      },
      {
        "title": "Выборка по статусу и периоду",
        "description": "Комбинируйте фильтры статуса с диапазоном дат (`>=DATE_CREATE`, `<=DATE_CREATE`) и пагинацией через `start`.",
        "order": {"DATE_CREATE": "DESC"},
        "filter": {
          "=STATUS_ID": "CONVERTED",
          ">=DATE_CREATE": "2024-05-01",
          "<=DATE_CREATE": "2024-05-31"
        },
        "limit": 100,
        "start": 0
      }
    ],
    "notes": [
      "Формат дат: ISO 8601 (`YYYY-MM-DD` или `YYYY-MM-DDThh:mm:ssZ`).",
      "Для свежих данных используйте `order = {\"DATE_MODIFY\": \"DESC\"}` и фильтры `>=DATE_CREATE`, `<=DATE_CREATE`.",
      "Полный ответ Bitrix24 всегда дублируется в structuredContent.result, пригодном для дальнейшей обработки агентом."
    ]
  },
  "toolWarnings": {
    "getLeads": [
      {
        "check": "require_date_range",
        "fields": ["DATE_CREATE", "DATE_MODIFY"],
        "message": "Добавьте фильтры диапазона (`>=DATE_CREATE` и `<=DATE_CREATE` либо аналогичные по DATE_MODIFY), чтобы ограничить выборку и повысить точность. Пример на текущий день: {{\">=DATE_CREATE\": \"{today_start}\", \"<=DATE_CREATE\": \"{today_end}\"}}.",
        "suggestion": "today",
        "suggestion_field": "DATE_CREATE",
        "suggested_filters": {
          ">=DATE_CREATE": "{today_start}",
          "<=DATE_CREATE": "{today_end}"
        }
      }
    ],
    "getDeals": [
      {
        "check": "require_date_range",
        "fields": ["DATE_CREATE", "DATE_MODIFY"],
        "message": "Добавьте фильтры диапазона (`>=DATE_CREATE` и `<=DATE_CREATE` либо аналогичные по DATE_MODIFY), чтобы ограничить выборку и повысить точность. Пример на текущий день: {{\">=DATE_CREATE\": \"{today_start}\", \"<=DATE_CREATE\": \"{today_end}\"}}.",
        "suggestion": "today",
        "suggestion_field": "DATE_CREATE",
        "suggested_filters": {
          ">=DATE_CREATE": "{today_start}",
          "<=DATE_CREATE": "{today_end}"
        }
      }
    ],
    "getContacts": [
      {
        "check": "require_date_range",
        "fields": ["DATE_CREATE", "DATE_MODIFY"],
        "message": "Добавьте фильтры диапазона (`>=DATE_CREATE` и `<=DATE_CREATE` либо аналогичные по DATE_MODIFY), чтобы ограничить выборку и повысить точность. Пример на текущий день: {{\">=DATE_CREATE\": \"{today_start}\", \"<=DATE_CREATE\": \"{today_end}\"}}.",
        "suggestion": "today",
        "suggestion_field": "DATE_CREATE",
        "suggested_filters": {
          ">=DATE_CREATE": "{today_start}",
          "<=DATE_CREATE": "{today_end}"
        }
      }
    ],
    "getTasks": [
      {
        "check": "require_date_range",
        "fields": ["CREATED_DATE", "CHANGED_DATE"],
        "message": "Добавьте фильтры диапазона (`>=CHANGED_DATE` и `<=CHANGED_DATE` либо аналогичные по CREATED_DATE), чтобы ограничить выборку и повысить точность. Используйте формат `YYYY-MM-DDTHH:MM:SS` без часового пояса. Пример на текущий день: {{\">=CHANGED_DATE\": \"{today_start_no_tz}\", \"<=CHANGED_DATE\": \"{today_end_no_tz}\"}}.",
        "suggestion": "today",
        "suggestion_field": "CHANGED_DATE",
        "suggestion_format": "datetime_no_tz",
        "suggested_filters": {
          ">=CHANGED_DATE": "{today_start_no_tz}",
          "<=CHANGED_DATE": "{today_end_no_tz}"
        }
      }
    ]
  },
  "tools": {
    "getDeals": {
      "description": "Получает сделки через `crm.deal.list`. Поддерживает выбор полей (`select`), фильтрацию с операторами Bitrix (`=` `>=` `<=` `@` и др.), сортировку (`order`), пагинацию (`start`) и ограничение количества (`limit`). Рекомендуется задавать явный диапазон дат по `DATE_CREATE` или `DATE_MODIFY`, чтобы избежать больших выборок.",
      "inputSchema": {
        "type": "object",
        "description": "Параметры запроса к `crm.deal.list`. Все ключи соответствуют REST API Bitrix24.",
        "additionalProperties": false,
        "properties": {
          "select": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Массив кодов полей. Если не задано, Bitrix24 вернёт набор по умолчанию.",
            "examples": [
              ["ID", "TITLE", "DATE_CREATE"],
              ["ID", "OPPORTUNITY", "ASSIGNED_BY_ID", "STAGE_ID"]
            ]
          },
          "filter": {
            "type": "object",
            "description": "Карта фильтров вида `<оператор><поле>` → значение. Операторы: `=` (точное), `>`/`>=`, `<`/`<=`, `@` (IN), `%` (LIKE). Для дат используйте `YYYY-MM-DD` или полный ISO 8601.",
            "examples": [
              {"=STAGE_ID": "NEW"},
              {">=DATE_MODIFY": "2024-05-01", "<=DATE_MODIFY": "2024-05-31"},
              {"@ASSIGNED_BY_ID": ["123", "456"]}
            ]
          },
          "order": {
            "type": "object",
            "description": "Сортировка: ключ — код поля, значение — направление.",
            "additionalProperties": {"type": "string", "enum": ["ASC", "DESC"]},
            "examples": [
              {"DATE_CREATE": "DESC"},
              {"ID": "ASC", "TITLE": "DESC"}
            ]
          },
          "start": {
            "type": "integer",
            "minimum": 0,
            "description": "Смещение для пагинации. Передавайте `next` из предыдущего ответа.",
            "examples": [0, 50]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 50,
            "description": "Максимум записей в одном ответе. Значения выше 500 будут усечены сервером.",
            "examples": [20, 50, 200]
          }
        },
        "examples": [
          {
            "select": ["ID", "TITLE", "DATE_CREATE"],
            "filter": {"=CATEGORY_ID": "0", ">=DATE_CREATE": "2024-01-01"},
            "order": {"DATE_CREATE": "DESC"},
            "limit": 20
          }
        ]
      }
    },
    "getLeads": {
      "description": "Получает лиды через `crm.lead.list`. Особенно полезно ограничивать диапазон по `DATE_CREATE` и сортировать по `DATE_MODIFY`, чтобы работать только с актуальными лидами. Все значения фильтров и сортировок соответствуют REST API Bitrix24.",
      "inputSchema": {
        "type": "object",
        "description": "Параметры запроса к `crm.lead.list`. Допускаются только перечисленные ключи.",
        "additionalProperties": false,
        "properties": {
          "select": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Массив кодов полей. Рекомендуемые поля: `ID`, `TITLE`, `DATE_CREATE`, `DATE_MODIFY`, `STATUS_ID`, `ASSIGNED_BY_ID`.",
            "examples": [
              ["ID", "TITLE", "DATE_CREATE", "STATUS_ID"],
              ["ID", "ASSIGNED_BY_ID", "PHONE", "EMAIL"]
            ]
          },
          "filter": {
            "type": "object",
            "description": "Фильтры формата `<оператор><поле>` → значение. Для диапазона дат используйте `>=DATE_CREATE` и `<=DATE_CREATE` либо поля `DATE_MODIFY`. Даты передавайте в ISO 8601.",
            "examples": [
              {"=STATUS_ID": "NEW"},
              {">=DATE_CREATE": "2024-06-01", "<=DATE_CREATE": "2024-06-02"},
              {"@ASSIGNED_BY_ID": ["123", "456"]}
            ]
          },
          "order": {
            "type": "object",
            "description": "Сортировка: `ASC` или `DESC` на каждое поле. Для свежих лидов используйте `DATE_MODIFY: DESC`.",
            "additionalProperties": {"type": "string", "enum": ["ASC", "DESC"]},
            "examples": [
              {"DATE_MODIFY": "DESC"},
              {"DATE_CREATE": "DESC", "ID": "ASC"}
            ]
          },
          "start": {
            "type": "integer",
            "minimum": 0,
            "description": "Смещение постраничного просмотра. Берите `next` из ответа Bitrix24.",
            "examples": [0, 50]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 50,
            "description": "Максимальное число записей. Значения свыше 500 автоматически усекутся.",
            "examples": [10, 20, 50, 100]
          }
        },
        "default": {
          "order": {"DATE_MODIFY": "DESC"},
          "limit": 50
        },
        "examples": [
          {
            "select": ["ID", "TITLE", "DATE_CREATE", "STATUS_ID"],
            "filter": {
              ">=DATE_CREATE": "2024-06-01",
              "<=DATE_CREATE": "2024-06-02",
              "=ASSIGNED_BY_ID": "123"
            },
            "order": {"DATE_MODIFY": "DESC"},
            "limit": 50
          }
        ]
      }
    },
    "getContacts": {
      "description": "Получает контакты через `crm.contact.list`. Используйте фильтры по `DATE_CREATE`, `DATE_MODIFY`, `ASSIGNED_BY_ID`, а также `@ID` для выборки по множеству идентификаторов.",
      "inputSchema": {
        "type": "object",
        "description": "Параметры запроса к `crm.contact.list`.",
        "additionalProperties": false,
        "properties": {
          "select": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Коды полей контакта (`ID`, `NAME`, `LAST_NAME`, `PHONE`, `EMAIL` и т.д.).",
            "examples": [
              ["ID", "NAME", "LAST_NAME", "DATE_CREATE"],
              ["ID", "PHONE", "EMAIL", "ASSIGNED_BY_ID"]
            ]
          },
          "filter": {
            "type": "object",
            "description": "Фильтры `<оператор><поле>` → значение. Для дат используйте ISO 8601.",
            "examples": [
              {"%NAME": "Иван"},
              {"@ID": ["10", "11", "12"]},
              {">=DATE_MODIFY": "2024-05-01", "<=DATE_MODIFY": "2024-05-31"}
            ]
          },
          "order": {
            "type": "object",
            "description": "Сортировка по полям контакта.",
            "additionalProperties": {"type": "string", "enum": ["ASC", "DESC"]},
            "examples": [
              {"DATE_CREATE": "DESC"},
              {"LAST_NAME": "ASC"}
            ]
          },
          "start": {
            "type": "integer",
            "minimum": 0,
            "description": "Смещение постраничного просмотра.",
            "examples": [0, 100]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 50,
            "description": "Количество контактов в ответе.",
            "examples": [50, 100, 200]
          }
        },
        "examples": [
          {
            "select": ["ID", "NAME", "PHONE"],
            "filter": {"%NAME": "Иван", ">=DATE_MODIFY": "2024-05-01"},
            "order": {"DATE_MODIFY": "DESC"},
            "limit": 50
          }
        ]
      }
    },
    "getUsers": {
      "description": "Получает пользователей портала через `user.get`. Можно выбирать поля (`select`) и фильтровать по активным/деактивированным пользователям.",
      "inputSchema": {
        "type": "object",
        "description": "Параметры запроса к `user.get`.",
        "additionalProperties": false,
        "properties": {
          "select": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Коды полей пользователя (`ID`, `NAME`, `LAST_NAME`, `WORK_POSITION`, `EMAIL`, `ACTIVE`).",
            "examples": [
              ["ID", "NAME", "LAST_NAME", "EMAIL"],
              ["ID", "WORK_POSITION", "DEPARTMENT", "ACTIVE"]
            ]
          },
          "filter": {
            "type": "object",
            "description": "Фильтры пользователя. Примеры: `=ACTIVE`, `@ID`, `%NAME`.",
            "examples": [
              {"=ACTIVE": "Y"},
              {"@ID": ["1", "2", "3"]},
              {"%NAME": "Сергей"}
            ]
          },
          "order": {
            "type": "object",
            "description": "Сортировка по полям пользователя.",
            "additionalProperties": {"type": "string", "enum": ["ASC", "DESC"]},
            "examples": [
              {"ID": "ASC"},
              {"NAME": "ASC"}
            ]
          },
          "start": {
            "type": "integer",
            "minimum": 0,
            "description": "Смещение постраничного просмотра.",
            "examples": [0, 100]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": 50,
            "description": "Количество пользователей в ответе.",
            "examples": [50, 100]
          }
        },
        "examples": [
          {
            "select": ["ID", "NAME", "WORK_POSITION", "ACTIVE"],
            "filter": {"=ACTIVE": "Y"},
            "order": {"ID": "ASC"},
            "limit": 100
          }
        ]
      }
    },
    "getTasks": {
      "description": "Получает задачи через `tasks.task.list`. Поддерживает фильтрацию по статусу, ответственному, дате создания/изменения и проектам (`GROUP_ID`).",
      "inputSchema": {
        "type": "object",
        "description": "Параметры запроса к `tasks.task.list`.",
        "additionalProperties": false,
        "properties": {
          "select": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Коды полей задачи. Примеры: `ID`, `TITLE`, `STATUS`, `RESPONSIBLE_ID`, `GROUP_ID`, `DEADLINE`.",
            "examples": [
              ["ID", "TITLE", "DEADLINE"],
              ["ID", "STATUS", "RESPONSIBLE_ID", "GROUP_ID"]
            ]
          },
          "filter": {
            "type": "object",
            "description": "Фильтры задач. Например `=STATUS`, `=RESPONSIBLE_ID`, `@GROUP_ID`, `>=CREATED_DATE`.",
            "examples": [
              {"=STATUS": "2"},
              {"=RESPONSIBLE_ID": "15"},
              {">=CREATED_DATE": "2024-06-01", "<=CREATED_DATE": "2024-06-02"}
            ]
          },
          "order": {
            "type": "object",
            "description": "Сортировка задач.",
            "additionalProperties": {"type": "string", "enum": ["ASC", "DESC"]},
            "examples": [
              {"DEADLINE": "ASC"},
              {"CREATED_DATE": "DESC"}
            ]
          },
          "start": {
            "type": "integer",
            "minimum": 0,
            "description": "Смещение постраничного просмотра.",
            "examples": [0, 100]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": 50,
            "description": "Количество задач в ответе.",
            "examples": [50, 100, 150]
          }
        },
        "examples": [
          {
            "select": ["ID", "TITLE", "STATUS", "RESPONSIBLE_ID"],
            "filter": {"=RESPONSIBLE_ID": "15", "=STATUS": "2"},
            "order": {"DEADLINE": "ASC"},
            "limit": 50
          }
        ]
      }
    }
  },
  "resources": {
    "crm/deals": {
      "name": "CRM Deals",
      "description": "Список сделок с фильтрами и пагинацией (crm.deal.list)."
    },
    "crm/leads": {
      "name": "CRM Leads",
      "description": "Список лидов с фильтрами и пагинацией (crm.lead.list)."
    },
    "crm/contacts": {
      "name": "CRM Contacts",
      "description": "Список контактов (crm.contact.list)."
    },
    "crm/users": {
      "name": "Portal Users",
      "description": "Список пользователей портала (user.get)."
    },
    "crm/tasks": {
      "name": "Tasks",
      "description": "Список задач (tasks.task.list)."
    },
    "bitrix24_leads_guide": {
      "descriptor": {
        "uri": "bitrix24_leads_guide",
        "name": "Шпаргалка по лидам",
        "description": "Готовые payload'ы для crm.lead.list, рекомендации по фильтрам и сортировкам."
      },
      "scenarios": [
        {
          "title": "Свежие лиды за 24 часа",
          "description": "Лиды, созданные за последние сутки, отсортированы по дате изменения.",
          "payload": {
            "order": {"DATE_MODIFY": "DESC"},
            "filter": {
              ">=DATE_CREATE": "2024-06-01T00:00:00Z",
              "<=DATE_CREATE": "2024-06-02T00:00:00Z"
            },
            "limit": 50
          }
        },
        {
          "title": "Лиды по статусу NEW за сегодня",
          "description": "Фильтрация по статусу NEW и датам создания на сегодняшний день.",
          "payload": {
            "order": {"DATE_CREATE": "DESC"},
            "filter": {
              "=STATUS_ID": "NEW",
              ">=DATE_CREATE": "2024-06-02T00:00:00Z",
              "<=DATE_CREATE": "2024-06-02T23:59:59Z"
            },
            "limit": 100
          }
        },
        {
          "title": "Лиды назначенные ответственному",
          "description": "Используйте массив идентификаторов для выборки по нескольким ответственным.",
          "payload": {
            "order": {"DATE_MODIFY": "DESC"},
            "filter": {
              "@ASSIGNED_BY_ID": ["123", "456"],
              ">=DATE_MODIFY": "2024-05-25",
              "<=DATE_MODIFY": "2024-05-31"
            },
            "limit": 200
          }
        }
      ],
      "rules": [
        "Комбинируйте фильтры по полям одного типа (`DATE_CREATE`, `DATE_MODIFY`) с одинаковыми операторами.",
        "Диапазон дат задавайте парой фильтров (`>=`, `<=`).",
        "Для пагинации используйте `start` из значения `next` предыдущего ответа."
      ]
    }
  }
}
-->

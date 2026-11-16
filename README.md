# sh-1c-report — 1C OData (atp_z2)

Закрытый проект для работы с OData-сервисом конфигурации **atp_z2**.

## Подключение

| Параметр | Значение |
|----------|----------|
| База | `http://172.16.35.29:8088/atp_z2` |
| OData | `…/odata/standard.odata/` |
| Пользователь | `Администратор` (в `.env`) |

Учётные данные хранятся только в `.env` (не коммитится). Скопируйте `.env.example` → `.env`.

## Сводка сущностей

| Тип | EntitySets |
|-----|------------|
| Document | 329 |
| Catalog | 328 |
| InformationRegister | 264 |
| Constant | 245 |
| AccumulationRegister | 92 |
| ChartOfCharacteristicTypes | 14 |
| DocumentJournal / ExchangePlan / BusinessProcess | по 5 |
| AccountingRegister | 4 |
| Task / ChartOfAccounts | по 3 |
| CalculationRegister | 2 |
| ChartOfCalculationTypes | 1 |

Всего: **1300** EntityType / EntitySet, **485** ComplexType, **266** Enum, **850** FunctionImport.

Подробности:

- `odata/OVERVIEW.md` — человекочитаемый каталог
- `odata/summary.json` — сводка
- `odata/catalog.json` — все объекты с полями
- `odata/entities/<Kind>.json` — по типам 1С
- `odata/metadata.xml` — сырой `$metadata`

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните пароль

# пример чтения справочника
python -m src.odata_client

# обновить метаданные и пересобрать каталог
python scripts/refresh_metadata.py
```

## Примеры запросов

```text
GET …/Catalog_Организации?$format=json&$top=10&$select=Ref_Key,Description,Code
GET …/Document_уатПутевойЛист?$format=json&$top=5&$orderby=Date desc
GET …/AccumulationRegister_Закупки_RecordType?$format=json&$top=20
```

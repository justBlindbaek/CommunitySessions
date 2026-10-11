# Breaking the Limits: Advanced Optimization of Semantic Models in Microsoft Fabric

Data Saturday Holland, Utrecht – 9 October 2026
Presented by Just Blindbæk and Greg Baldini

- Session: [Breaking the Limits: Advanced Optimization of Semantic Models in Microsoft Fabric](https://sessionize.com/s/justB/breaking-the-limits-advanced-optimization-of-seman/169980)
- Slides: [Advanced Optimization of Semantic Models in Microsoft Fabric.pdf](Advanced%20Optimization%20of%20Semantic%20Models%20in%20Microsoft%20Fabric.pdf)

## Demo dataset

Most demos in the session use a semantic model built on the NYC Yellow Taxi trip data. The Scale-Out demo has its own small model, which is included. You can build the same lab in your own Fabric workspace by following the blog post [Building a Fabric Lab for Semantic Model Memory Experiments](https://justb.dk/blog/2026/02/building-a-fabric-lab-for-semantic-model-memory-experiments-with-help-from-chatgpt/).

## Demos

The demos are listed in the order they appear in the session.

- [User-defined aggregations](#demo-user-defined-aggregations)
- [Direct Lake: column loading and temperature](#demo-direct-lake-column-loading-and-temperature)
- [Semantic Model Refresh Scale-Out](#demo-semantic-model-refresh-scale-out)
- [DAX query optimization in DAX Studio](#demo-dax-query-optimization-in-dax-studio)

## Demo: User-defined aggregations

The aggregations demo used a Tabular Editor C# script that sets up user-defined aggregations on a fact table automatically. It clones the fact table into a hidden DirectQuery detail table, sets the related dimensions to Dual storage mode, and configures **Alternate Of** on the aggregated columns.

The script and a full walkthrough are in the Tabular Editor docs: [Implement user-defined aggregations](https://docs.tabulareditor.com/en/features/CSharpScripts/Advanced/script-implement-user-defined-aggregations.html).

## Demo: Direct Lake: column loading and temperature

A Direct Lake model only loads a column into memory when a query needs it (transcoding). The [`direct-lake`](direct-lake) folder has the two queries used to show this in DAX Studio, connected to a Direct Lake version of the Yellow Taxi model:

| File | What it does |
|------|--------------|
| [`column-temperature-dmv.dax`](direct-lake/column-temperature-dmv.dax) | Queries the `DISCOVER_STORAGE_TABLE_COLUMNS` DMV to show, for each column, whether it is loaded in memory (`DICTIONARY_ISRESIDENT`), its temperature and when it was last accessed |
| [`query-direct-lake-model.dax`](direct-lake/query-direct-lake-model.dax) | A simple query by year that uses a few of the model's columns |

For example, run the DMV query on a model that was just reframed and few or no columns are resident. Run the second query, then the DMV query again: the columns that the query used are now loaded and have a temperature.

## Demo: Semantic Model Refresh Scale-Out

[`semantic-model-refresh-scale-out-demo.py`](scale-out/semantic-model-refresh-scale-out-demo.py) walks through how to use semantic model scale-out to reduce the memory needed to refresh a semantic model.

During a normal full refresh, the old data stays in memory while the new data is loaded, so the refresh can need about twice the memory of the model. With scale-out turned on and auto sync turned off, report users are served by a read-only replica. You can then:

1. Empty the read-write replica with a `clearValues` refresh, which frees its memory.
2. Run a full refresh on the empty read-write replica.
3. Sync the read-write replica to the read-only replica when the refresh has finished.

Users keep querying the old data the whole time and never see an empty model.

You can read the full background in the blog post [Using Semantic Model Scale-Out to Reduce Refresh Memory in Fabric](https://justb.dk/blog/2026/03/using-semantic-model-scale-out-to-reduce-refresh-memory-in-fabric/).

### ⚠ Use a test model

Step 0 changes the scale-out settings of the model, and Step 1 empties it. Only run the script against a demo or test model, and run the **Reset** cell at the end to restore the settings.

### Prerequisites

- The semantic model is on a Fabric (F SKU) or Power BI Premium capacity.
- The model uses the **large semantic model storage format**.
- You have write access to the model. Changing the scale-out settings through the API may require you to be the model owner.
- Python 3.10 or later.
- The [Fabric CLI](https://microsoft.github.io/fabric-cli/), installed and signed in:

  ```bash
  pip install ms-fabric-cli
  fab auth login
  ```

The script only uses the Python standard library. All API calls go through `fab api`, so the Fabric CLI handles authentication.

### Demo model

[`semantic-model-refresh-scale-out-demo.bim`](scale-out/semantic-model-refresh-scale-out-demo.bim) is a tiny semantic model with one table, `RefreshInfo`, which holds one row with the time of the last refresh. The table is created inline in Power Query, so the model has no data source and refreshes without credentials.

1. Deploy the model to a workspace on a Fabric or Premium capacity, for example with [Tabular Editor](https://tabulareditor.com/) through the workspace's XMLA endpoint. The XMLA endpoint must allow read-write.
2. In the model settings, check that **Large semantic model storage format** is turned on.
3. Refresh the model once.
4. Create a report on the model with a card that shows `RefreshTime`.

The report keeps showing the old refresh time through steps 1 and 2 of the script, and only shows the new time after the sync in step 4. `RefreshTime` is in UTC. The Power Query expression has a comment showing how to switch to local time.

### How to run it

1. Open the script in VS Code with the **Python** and **Jupyter** extensions installed.
2. Fill in `WORKSPACE_ID` and `DATASET_ID` in the Setup cell. Both are in the URL of the semantic model in the Fabric portal:
   `https://app.fabric.microsoft.com/groups/<WORKSPACE_ID>/datasets/<DATASET_ID>/details`
3. Run one cell at a time with **Run Cell** (Shift+Enter), starting with the Setup cell.

| Step | What                | GUI alternative                                  |
|------|---------------------|--------------------------------------------------|
| -    | Check status        | Model settings > Query scale-out                 |
| 0    | Enable scale-out    | Model settings > Query scale-out (auto sync off) |
| 1    | clearValues         | -                                                |
| 2    | Full refresh        | Refresh now in the workspace                     |
| 3    | Observe out-of-sync | -                                                |
| 4    | Trigger sync        | -                                                |
| 5    | Verify alignment    | -                                                |
| -    | Reset (disable)     | Model settings > Query scale-out: Off            |

### In production

In real use you would chain the `clearValues` refresh, the full refresh and the sync in a pipeline or notebook. With auto sync off, report users don't see new data until you trigger the sync.

## Demo: DAX query optimization in DAX Studio

The [`dax`](dax) folder has the DAX queries Greg used in DAX Studio to show how rewriting a query can make it faster. Each file has two versions of the same query: the slow version at the top, and the optimized version further down after a block of empty lines. Both versions return the same result.

| File | Slow version | Optimization technique |
|------|--------------|------------------------|
| [`counting.dax`](dax/counting.dax) | Counts tipped trips with `SUMX` and an `IF` that is evaluated for every row of the fact table | Move the condition into the filter context: `CALCULATE ( COUNTROWS ( ... ), <condition> )` |
| [`distance-bands-switch.dax`](dax/distance-bands-switch.dax) | Works out each trip's distance band with `SWITCH`, then matches it to the band | Use each band's low and high limits as filter predicates in `CALCULATE` |
| [`long-trips-repeat-filters.dax`](dax/long-trips-repeat-filters.dax) | Filters the fact table on a measure, so the measure is evaluated once per trip (context transition on every row) | Repeat the filter predicates instead of filtering on a measure |
| [`rush-hour-materialize-flags.dax`](dax/rush-hour-materialize-flags.dax) | Works out rush hour and weekday from the fact table's columns in DAX | Use flag columns that already exist in the `Time` and `Date` tables, and let the relationships and the storage engine do the filtering |

The queries run against the Yellow Taxi model described in [Demo dataset](#demo-dataset). You can also use them as patterns to apply to your own model.

To compare the two versions, run each one in DAX Studio with **Server Timings** turned on, and compare the total duration and how much of it is spent in the formula engine versus the storage engine.

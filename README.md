# TerraWalk AI

Прототип четвёртого сервиса: спутниковая карта, выбор точки, OpenWeather, 3D-панорама из 4×4 тайлов, виртуальный джойстик, управление камерой, Groq AI, Cloudflare AI sky и MongoDB.

## Render
Build: `pip install -r requirements.txt`
Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Environment Variables:
- `OPENWEATHER_API_KEY`
- `GROQ_API_KEY`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_KEY` (или `CLOUDFLARE_API_TOKEN`)
- `MONGODB_URI` (необязательно; история сохраняется в базе `terra_walk_ai`, коллекция `visits`)

## Важное ограничение
Esri World Imagery даёт спутниковые изображения, а AWS Terrain Tiles — цифровую модель рельефа. Это позволяет построить 3D-поверхность земли, но не создаёт настоящую геометрию домов. Персонаж в этой версии стилизованный, а не фотограмметрическая модель. Для реальных 3D-зданий нужны отдельные лицензированные 3D Tiles/модели с подходящим покрытием. Кнопка генерации неба пока показывает Cloudflare-изображение поверх основной карты; подключение его как текстуры неба в 3D-сцене — следующий этап. Переключатель стиля карты пока информационный.

# デモ版(Vercelデプロイ用)

実機・rosbridgeが無くても操縦者が練習できるように、`web/robot-console.html`をそのまま
静的サイトとしてデプロイできる形に置いたフォルダです。中身はコード的に本番と同一で、
「デモ」チェックボックスがONの状態がデフォルトなので、開けばそのまま練習用シミュレーションが動きます
(スティック入力に応じて画面内の疑似位置が動くだけで、実際のロボット・rosbridgeへの接続は行いません)。

## 中身
- `index.html`(`web/robot-console.html`のコピー)
- `roslib.min.js`
- `CITRobocon_image.jpg` / `con_image.jpg`

`web/robot-console.html`を更新したら、このフォルダの`index.html`にも同じ内容をコピーしてください。

## Vercelへのデプロイ手順

### 方法A: VercelダッシュボードからGitHub連携(推奨、CLI不要)
1. https://vercel.com にログイン(GitHubアカウントでOK)
2. 「Add New...」→「Project」→このリポジトリ(`Phone_Controller`)をImport
3. **Root Directory** を `demo-web` に設定(重要。これを忘れると`web/`ごとデプロイされてしまう)
4. Framework Presetは「Other」のままでOK(ビルド不要の静的サイトなので、Build CommandやOutput Directoryは空でよい)
5. Deploy。以後`main`にpushするたびに自動で再デプロイされる

### 方法B: Vercel CLIから直接
```bash
cd demo-web
npx vercel        # 初回はログイン・プロジェクト作成のプロンプトが出る
npx vercel --prod # 本番URLに反映
```

どちらの方法でも、発行されたURLをそのまま操縦者に共有すればスマホのブラウザで開けます。

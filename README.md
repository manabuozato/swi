# Super Watareck Video Editor (SWI)

SWIは、vlog制作に特化したシンプルなWebベースのビデオ編集ツールです。

## 主要機能

1. 動画のアップロードと管理
2. 複数動画の順番入れ替えと結合
3. テキストオーバーレイの追加
4. オーディオ処理（LUFSノーマライズ）

## セットアップ

1. リポジトリをクローンします：
git clone https://github.com/manabuozato/swi.git
cd swi

2. 仮想環境を作成し、アクティベートします：
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate

3. 必要なパッケージをインストールします：
pip install -r requirements.txt

4. アプリケーションを実行します：
python app.py

5. ブラウザで `http://localhost:5001` を開きます。

## 使用方法

1. 「アップロード」ボタンをクリックして動画をアップロードします。
2. アップロードした動画を並び替えます。
3. 必要に応じてテキストオーバーレイを追加します。
4. 「結合する」ボタンをクリックして動画を結合します。

## ライセンス
このプロジェクトはMITライセンスの下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。
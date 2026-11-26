package local.sanguo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.neo4j.configuration.GraphDatabaseSettings;
import org.neo4j.configuration.connectors.BoltConnector;
import org.neo4j.configuration.connectors.HttpConnector;
import org.neo4j.configuration.helpers.SocketAddress;
import org.neo4j.harness.Neo4j;
import org.neo4j.harness.Neo4jBuilders;

/**
 * 内嵌 Neo4j 启动器：真实内核 + 标准 Bolt/HTTP 端口，供没有安装 Neo4j 的机器使用。
 *
 * 用法：mvn -q compile exec:java -Dexec.args="数据目录 bolt端口 http端口"
 * 默认：          mvn -q compile exec:java
 *       数据目录 dev/neo4j-embed/target/neo4j-home，bolt 7687，http 7474
 */
public final class EmbedServer {

    private EmbedServer() {
    }

    public static void main(String[] args) throws Exception {
        Path home = Paths.get(args.length > 0 ? args[0] : "target/neo4j-home");
        int boltPort = args.length > 1 ? Integer.parseInt(args[1]) : 7687;
        int httpPort = args.length > 2 ? Integer.parseInt(args[2]) : 7474;

        Files.createDirectories(home);

        // harness 每次启动都会在 home 下新建一个随机名子目录，数据跟着就换地方了，
        // 重启等于空库。把 data_directory 钉死在 home/data，重启才能复用。
        Path dataDir = home.resolve("data").toAbsolutePath();

        Neo4j server = Neo4jBuilders.newInProcessBuilder(home)
                .withConfig(GraphDatabaseSettings.auth_enabled, false)
                .withConfig(GraphDatabaseSettings.data_directory, dataDir)
                .withConfig(BoltConnector.enabled, true)
                .withConfig(BoltConnector.listen_address, new SocketAddress("127.0.0.1", boltPort))
                .withConfig(BoltConnector.advertised_address, new SocketAddress("127.0.0.1", boltPort))
                .withConfig(HttpConnector.enabled, true)
                .withConfig(HttpConnector.listen_address, new SocketAddress("127.0.0.1", httpPort))
                .withConfig(HttpConnector.advertised_address, new SocketAddress("127.0.0.1", httpPort))
                .build();

        Runtime.getRuntime().addShutdownHook(new Thread(server::close));

        System.out.println("[embed] neo4j 5.26 已启动（认证已关闭，密码随便填）");
        System.out.println("[embed] 数据目录 " + home.toAbsolutePath());
        System.out.println("[embed] bolt    " + server.boltURI());
        System.out.println("[embed] http    " + server.httpURI());
        System.out.println("[embed] Ctrl+C 停止；重启会复用同一数据目录");
        System.out.flush();

        Thread.currentThread().join();
    }
}

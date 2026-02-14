import elasticLogo from "@/assets/icons8-elasticsearch-144.png";

export default function ElasticIcon({ size = 16 }: { size?: number }) {
  return (
    <img
      src={elasticLogo}
      alt="Elastic"
      width={size}
      height={size}
      className="inline-block shrink-0"
      style={{ objectFit: "contain" }}
    />
  );
}
